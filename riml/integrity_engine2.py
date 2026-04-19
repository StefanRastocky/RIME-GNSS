import time
from dataclasses import dataclass, field
from collections import defaultdict, deque
from typing import Any, Optional


# GNSS constellation decoding
GNSS_MAP = {
    0: "GPS",
    1: "SBAS",
    2: "GALILEO",
    3: "BEIDOU",
    4: "IMES",
    5: "QZSS",
    6: "GLONASS",
}


def gnss_name(gnss_id: int) -> str:
    return GNSS_MAP.get(gnss_id, f"GNSS{gnss_id}")


def make_key(gnss_id: int, sv_id: int, band: Optional[str] = None):
    """Signal identity key. Band is optional for now."""
    return (gnss_id, sv_id, band)


def key_sort_key(key):
    """Sort by constellation, SV, band"""
    gnss_id = key[0]
    sv_id = key[1]
    band = key[2] if len(key) > 2 else None
    return (gnss_id, sv_id, band or "")

def key_label(key) -> str:
    gnss_id = key[0]
    sv_id = key[1]
    band = key[2] if len(key) > 2 else None
    band_txt = f"/{band}" if band else ""
    return f"{gnss_name(gnss_id)}\tsv{sv_id} {band_txt}"


@dataclass(frozen=True)
class MetricSpec:
    threshold: float
    hysteresis: float = 0.0
    direction: str = "low"   # "low" = bad if value < threshold, "high" = bad if value > threshold
    weight: int = 1
    bad_event: str = ""
    recover_event: str = ""


@dataclass
class SignalState:
    seen: bool = False
    first_seen_ts: float = 0.0
    last_seen_ts: float = 0.0

    values: dict[str, Any] = field(default_factory=dict)
    prev_values: dict[str, Any] = field(default_factory=dict)
    flags: dict[str, bool] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


class UBXIntegrityEngine:
    def __init__(self, console_out: bool = False, loss_timeout: float = 5.0, event_log_size: int = 100):
        self.console_output = console_out
        self.loss_timeout = loss_timeout

        self.signals = defaultdict(SignalState)
        self.events = deque(maxlen=event_log_size)

        self.metric_specs = {
            "elev": MetricSpec(
                threshold=10,
                hysteresis=2,
                direction="low",
                weight=1,
                bad_event="LOW_ELEV",
                recover_event="ELEV_RECOV",
            ),
            "snr": MetricSpec(
                threshold=25,
                hysteresis=3,
                direction="low",
                weight=2,
                bad_event="LOW_SNR",
                recover_event="SNR_RECOV",
            ),
            "prRes": MetricSpec(
                threshold=10,
                hysteresis=1.0,
                direction="high",
                weight=3,
                bad_event="HIGH_RESIDUAL",
                recover_event="RESIDUAL_RECOV"),
        }

    def ingest(self, ts, msg):
        if msg.identity == "NAV-SAT":
            self._handle_nav_sat(ts, msg)
        # elif msg.identity == "RXM-RAWX":
        #     self._handle_rawx(ts, msg)

    def _iter_nav_sat_entries(self, msg):
        n = getattr(msg, "numSvs", 0)

        fields = ("gnssId", "svId", "cno", "elev", "prRes", "qualityInd", "svUsed", "health") #removed "azim"

        for i in range(1, n + 1):
            suf = f"_{i:02d}"
            entry = {}
            for name in fields:
                entry[name] = getattr(msg, f"{name}{suf}", None)
            yield entry

    def _handle_nav_sat(self, ts, msg):
        active_now = set()

        for s in self._iter_nav_sat_entries(msg):
            gnss = s["gnssId"]
            svid = s["svId"]
            if gnss is None or svid is None:
                continue

            band = s.get("band")  # NAV-SAT does not provide band - see RXM_SFRBX
            key = make_key(gnss, svid, band)
            active_now.add(key)

            fields = {
                "snr": s.get("cno"),
                "elev": s.get("elev"),
                #"azim": s.get("azim"),
                "prRes": s.get("prRes"),
                "qualityInd": s.get("qualityInd"),
                "svUsed": s.get("svUsed"),
                "health": s.get("health"),
            }
            fields = {k: v for k, v in fields.items() if v is not None}

            self.update_signal(key, ts, source="NAV-SAT", **fields)

        self._detect_losses(ts, active_now)

    def update_signal(self, key, ts, source: Optional[str] = None, **fields):
        """
        Generic signal update.
        Handler extracts message-specific fields and passes them here.
        """
        state = self.signals[key]

        if not state.seen:
            state.seen = True
            state.first_seen_ts = ts
            self._emit(ts, key, "ACQUIRED")

        # Keep a copy of the old values before overwriting them.
        state.prev_values = state.values.copy()
        state.values.update(fields)
        state.last_seen_ts = ts

        if source is not None:
            state.meta["source"] = source

        self._evaluate_rules(ts, key, state)

        return state

    def _evaluate_rules(self, ts, key, state: SignalState):
        """
        Generic threshold/hysteresis engine.
        Direction controls whether low or high is considered bad.
        """
        for name, spec in self.metric_specs.items():
            value = state.values.get(name)
            if value is None:
                continue

            flag_name = f"bad_{name}"
            was_bad = state.flags.get(flag_name, False)

            if spec.direction == "low":
                is_bad = value < spec.threshold
                recovered = value >= (spec.threshold + spec.hysteresis)
            else:
                is_bad = value > spec.threshold
                recovered = value <= (spec.threshold - spec.hysteresis)

            if (not was_bad) and is_bad:
                state.flags[flag_name] = True
                event = spec.bad_event or f"BAD_{name.upper()}"
                self._emit(ts, key, event, value, spec.threshold)

            elif was_bad and recovered:
                state.flags[flag_name] = False
                event = spec.recover_event or f"{name.upper()}_RECOV"
                self._emit(ts, key, event, value, spec.threshold)

            health = state.values.get("health")

            if health is not None:
                was_bad = state.flags.get("bad_health", False)
                is_bad = (health != 1)
            
                if (not was_bad) and is_bad:
                    state.flags["bad_health"] = True
                    self._emit(ts, key, "BAD_HEALTH", health, 1)
            
                elif was_bad and not is_bad:
                    state.flags["bad_health"] = False
                    self._emit(ts, key, "HEALTH_RECOV", health, 1)

    def _detect_losses(self, ts, active_now):
        for key, state in self.signals.items():
            if not state.seen:
                continue

            if key not in active_now and (ts - state.last_seen_ts) > self.loss_timeout:
                self._emit(ts, key, "LOST")
                state.seen = False

    def _severity(self, state: SignalState) -> int:
        score = 0
        for name, spec in self.metric_specs.items():
            if state.flags.get(f"bad_{name}", False):
                score += spec.weight
        if state.values.get("prRes") is not None and abs(state.values.get("prRes")) > 10:
            score += 5
        return score

    def _include_in_pvt(self, state: SignalState) -> bool:
        if not state.seen:
            return False

        if state.flags.get("bad_health", False):
            return False

        if state.flags.get("bad_prRes", False):
            return False
        return self._severity(state) < 3

    def build_state_matrix(self):
        """
        Returns a JSON-ready list of per-signal rows.
        This is what the glue/frontend should render.
        """
        rows = []

        for key in sorted(self.signals.keys(), key=key_sort_key):
            state = self.signals[key]
            age_s = None if not state.seen else max(0.0, time.monotonic() - state.last_seen_ts)

            row = {
                "key": key,
                "label": key_label(key),
                "gnss": gnss_name(key[0]),
                "gnss_id": key[0],
                "sv_id": key[1],
                "band": key[2] if len(key) > 2 else None,
                "seen": state.seen,
                "age_s": age_s,
                "first_seen_ts": state.first_seen_ts,
                "last_seen_ts": state.last_seen_ts,
                "severity": self._severity(state),
                "include_in_pvt": self._include_in_pvt(state),
                "values": dict(state.values),
                "flags": dict(state.flags),
                "meta": dict(state.meta),
            }

            # Flatten the current values/flags into the row too, so a table renderer can use them directly.
            for k, v in state.values.items():
                row[k] = v
            for k, v in state.flags.items():
                row[k] = v

            rows.append(row)

        return rows

    def snapshot(self):
        """
        Full payload for glue/UI.
        """
        return {
            "ts": time.monotonic(),
            "matrix": self.build_state_matrix(),
            "events": list(self.events),
        }

    def _format_event(self, ts, key, event, value=None, threshold=None):
        label = key_label(key)
        if value is None:
            return f"{ts:10.3f}\t{label:<18}\t{event}"
        return f"{ts:10.3f}\t{label:<18}\t{event:<16}\tcur={value!s:<6}\tthr={threshold!s:<6}"

    def _emit(self, ts, key, event, value=None, threshold=None):
        record = {
            "ts": ts,
            "key": key,
            "label": key_label(key),
            "event": event,
            "value": value,
            "threshold": threshold,
        }
        self.events.append(record)

        if self.console_output:
            print(self._format_event(ts, key, event, value, threshold))
