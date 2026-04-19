from serial import Serial
from pyubx2 import (
    UBXReader, UBXMessage,
    UBX_PROTOCOL, NMEA_PROTOCOL,
    POLL_LAYER_RAM, SET_LAYER_RAM, TXN_NONE,
)

PORT = "/dev/ttyACM0"


def pretty_print(msg):
    print(f"\n=== {msg.identity} ===")
    if hasattr(msg, "cfgData"):
        # CFG-VALGET responses usually contain key/value tuples
        for item in msg.cfgData:
            try:
                k, v = item
                print(f"{k:<40} {v}")
            except Exception:
                print(item)
    else:
        for k, v in vars(msg).items():
            if not k.startswith("_"):
                print(f"{k:<25}: {v}")


def send_and_wait(ser, ubr, msg, expect):
    ser.write(msg.serialize())
    while True:
        raw, parsed = ubr.read()
        if parsed is None:
            continue
        pretty_print(parsed)
        if parsed.identity == expect:
            return parsed


with Serial(PORT, 115200, timeout=2) as ser:
    ubr = UBXReader(ser, protfilter=UBX_PROTOCOL | NMEA_PROTOCOL)

    # POLL EVERYTHING RELATED TO MSG OUTPUT (USB included)
    poll_all = UBXMessage.config_poll(
        POLL_LAYER_RAM,
        0,
        [0x2091FFFF]   # CFG-MSGOUT wildcard
    )

    print("\n--- BEFORE CONFIG ---")
    send_and_wait(ser, ubr, poll_all, "CFG-VALGET")

    # APPLY CONFIG (disable NMEA, enable UBX NAV + RXM + MON)
    set_pairs = [
        # disable all NMEA (USB)
        ("CFG_MSGOUT_NMEA_ID_GGA_USB", 0),
        ("CFG_MSGOUT_NMEA_ID_GLL_USB", 0),
        ("CFG_MSGOUT_NMEA_ID_GSA_USB", 0),
        ("CFG_MSGOUT_NMEA_ID_GSV_USB", 0),
        ("CFG_MSGOUT_NMEA_ID_RMC_USB", 0),
        ("CFG_MSGOUT_NMEA_ID_VTG_USB", 0),
        ("CFG_MSGOUT_NMEA_ID_ZDA_USB", 0),

        # enable UBX NAV
        ("CFG_MSGOUT_UBX_NAV_PVT_USB", 1),
        ("CFG_MSGOUT_UBX_NAV_SAT_USB", 1),
        ("CFG_MSGOUT_UBX_NAV_STATUS_USB", 1),

        # enable raw / measurement
        ("CFG_MSGOUT_UBX_RXM_RAWX_USB", 1),
        ("CFG_MSGOUT_UBX_RXM_SFRBX_USB", 1),

        # optional diagnostics
        ("CFG_MSGOUT_UBX_MON_RF_USB", 1),
    ]

    print("\n--- APPLYING CONFIG ---")
    setmsg = UBXMessage.config_set(SET_LAYER_RAM, TXN_NONE, set_pairs)
    send_and_wait(ser, ubr, setmsg, "ACK-ACK")

    # VERIFY AGAIN (same wildcard poll)
    print("\n--- AFTER CONFIG ---")
    send_and_wait(ser, ubr, poll_all, "CFG-VALGET")
