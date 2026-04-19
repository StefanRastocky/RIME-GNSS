from serial import Serial
from pyubx2 import (
    UBXReader, UBXMessage,
    UBX_PROTOCOL, NMEA_PROTOCOL,
    SET_LAYER_RAM, POLL_LAYER_RAM, TXN_NONE,
)

PORT = "/dev/ttyACM0"   # change to your USB serial device

# Poll the active RAM state for USB protocol and message-output keys.
USB_CFG_KEYS = [
    0x10780001,  # CFG-USBOUTPROT-UBX
    0x10780002,  # CFG-USBOUTPROT-NMEA
    0x20910009,  # CFG-MSGOUT-UBX_NAV_PVT_USB
    0x20910018,  # CFG-MSGOUT-UBX_NAV_SAT_USB
    0x209102A7,  # CFG-MSGOUT-UBX_RXM_RAWX_USB
    0x20910234,  # CFG-MSGOUT-UBX_RXM_SFRBX_USB
]

# New RAM-only configuration: UBX on, NMEA off, selected UBX messages on.
USB_CFG_SET = [
    (0x10780001, 1),
    (0x10780002, 0),
    (0x20910009, 1),
    (0x20910018, 1),
    (0x209102A7, 1),
    (0x20910234, 1),
]

def send_and_wait(ser, ubr, msg, expect_identity):
    ser.write(msg.serialize())
    while True:
        raw, parsed = ubr.read()
        if parsed is None:
            continue
        print(parsed)
        if parsed.identity == expect_identity:
            return parsed

with Serial(PORT, baudrate=115200, timeout=2) as ser:
    ubr = UBXReader(ser, protfilter=UBX_PROTOCOL | NMEA_PROTOCOL)

    # 1) poll initial state
    poll1 = UBXMessage.config_poll(POLL_LAYER_RAM, 0, USB_CFG_KEYS)
    send_and_wait(ser, ubr, poll1, "CFG-VALGET")

    # 2) apply new config to RAM
    setmsg = UBXMessage.config_set(SET_LAYER_RAM, TXN_NONE, USB_CFG_SET)
    send_and_wait(ser, ubr, setmsg, "ACK-ACK")

    # 3) poll again to verify
    poll2 = UBXMessage.config_poll(POLL_LAYER_RAM, 0, USB_CFG_KEYS)
    send_and_wait(ser, ubr, poll2, "CFG-VALGET")
