import time
from collections import defaultdict


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


# State machine per SV
class SignalState:
    def __init__(self):
        self.seen = False
        self.last_seen = 0.0

        self.elev = None
        self.snr = None

        # hysteresis state (important!)
        self.low_snr = False
        self.low_elev = False


# Engine
class UBXIntegrityEngine:
    def __init__(self, console_out=False):
        self.console_output = console_out
        self.signals = defaultdict(SignalState)
        self.events = []

        # thresholds
        self.MIN_ELEV = 10
        self.MIN_SNR = 25

        # hysteresis margins (prevents flicker)
        self.ELEV_HYST = 2
        self.SNR_HYST = 2

        self.LOSS_TIMEOUT = 5.0

    def ingest(self, ts, msg):
        if msg.identity == "NAV-SAT":
            self._handle_nav_sat(ts, msg)

    # NAV-SAT parsing
    def _iter_nav_sat_entries(self, msg):
        n = getattr(msg, "numSvs", 0)

        for i in range(1, n + 1):
            suf = f"_{i:02d}"
            yield {
                "gnssId": getattr(msg, f"gnssId{suf}", None),
                "svId": getattr(msg, f"svId{suf}", None),
                "cno": getattr(msg, f"cno{suf}", None),
                "elev": getattr(msg, f"elev{suf}", None),
            }

    def _handle_nav_sat(self, ts, msg):
        active_now = set()

        for s in self._iter_nav_sat_entries(msg):
            gnss = s["gnssId"]
            svid = s["svId"]
            elev = s["elev"]
            snr = s["cno"]

            if gnss is None or svid is None:
                continue

            key = (gnss, svid)
            state = self.signals[key]
            active_now.add(key)

            # first seen
            if not state.seen:
                self._emit(ts, key, "ACQUIRED")

            # update state
            prev_elev = state.elev
            prev_snr = state.snr

            state.seen = True
            state.last_seen = ts
            state.elev = elev
            state.snr = snr

            # LOW ELEVATION (hysteresis)
            self._update_threshold(
                ts,
                key,
                state,
                prev=prev_elev,
                curr=elev,
                low_flag="low_elev",
                event_low="LOW_ELEV",
                event_rec="ELEV_RECOV",
                threshold=self.MIN_ELEV,
                hysteresis=self.ELEV_HYST,
                is_snr=False,
            )

            # LOW SNR (hysteresis)
            self._update_threshold(
                ts,
                key,
                state,
                prev=prev_snr,
                curr=snr,
                low_flag="low_snr",
                event_low="LOW_SNR\t",
                event_rec="SNR_RECOV",
                threshold=self.MIN_SNR,
                hysteresis=self.SNR_HYST,
                is_snr=True,
            )

        self._detect_losses(ts, active_now)

    # Core hysteresis logic
    def _update_threshold(
        self,
        ts,
        key,
        state,
        prev,
        curr,
        low_flag,
        event_low,
        event_rec,
        threshold,
        hysteresis,
        is_snr,
    ):
        if curr is None:
            return

        low_now = curr < threshold
        was_low = getattr(state, low_flag)

        # enter low state (edge)
        if (not was_low) and low_now:
            setattr(state, low_flag, True)
            self._emit(ts, key, event_low, curr, threshold)

        # exit low state (with hysteresis)
        elif was_low and curr >= (threshold + hysteresis):
            setattr(state, low_flag, False)
            self._emit(ts, key, event_rec, curr, threshold)

    # Loss detection
    def _detect_losses(self, ts, active_now):
        for key, state in self.signals.items():
            if not state.seen:
                continue

            if key not in active_now and (ts - state.last_seen) > self.LOSS_TIMEOUT:
                self._emit(ts, key, "LOST")
                state.seen = False

    # Logging
    def _emit(self, ts, key, event, value=None, threshold=None):
        gnss, svid = key
        cname = gnss_name(gnss)

        record = (ts, key, event, value, threshold)
        self.events.append(record)

        if self.console_output:
            if value is None:
                print(f"{ts:.3f}\t{cname}\tsv{svid}\t{event} ")
            else:
                print(
                    f"{ts:.3f}\t{cname}\tsv{svid}\t{event}\t"
                    f"(current={value},\tthreshold={threshold})"
            )
