import time
import threading
import queue
import serial
from pyubx2 import UBXReader, UBXMessage

PORT = "/dev/ttyACM0"
BAUD = 115200

rxq = queue.Queue()
stop_evt = threading.Event()


def rx_loop(reader, ser):
    print("[RX] Receive loop thread started")
    try:
        while not stop_evt.is_set():
            raw, msg = reader.read()
            if msg is not None:
                rxq.put((time.time(), msg))

    except Exception as e:
        print("[RX ERROR]", e)

    finally:
        try:
            ser.close()
            print("[RX] serial closed")
        except Exception as e:
            print("[RX] serial close error:", e)

        print("[RX] thread stopped cleanly")



def valset(serPort, items, layers=1):
    if isinstance(items, tuple):
        items = [items]
    msg = UBXMessage.config_set(layers, 0, list(items))
    serPort.write(msg.serialize())


def run_ubx_monitor():
    ser = serial.Serial(PORT, BAUD, timeout=1)

    # UBX only
    reader = UBXReader(ser, protfilter=2)

    t = threading.Thread(target=rx_loop, args=(reader, ser), daemon=True)
    t.start()
    print("[RX] Daemon running")

    # interesting UBX messages for USB (hardcoded for now
    # should be placed in a separate riml/ubx_config.py module
    interest = [
        #"CFG_MSGOUT_UBX_MON_HW_USB",
        #"CFG_MSGOUT_UBX_MON_IO_USB",
        "CFG_MSGOUT_UBX_MON_RF_USB",
        "CFG_MSGOUT_UBX_NAV_DOP_USB",
        "CFG_MSGOUT_UBX_NAV_POSECEF_USB",
        "CFG_MSGOUT_UBX_NAV_PVT_USB",
        "CFG_MSGOUT_UBX_NAV_SAT_USB",
        "CFG_MSGOUT_UBX_NAV_STATUS_USB",
        #"CFG_MSGOUT_UBX_NAV_VELNED_USB",
        "CFG_MSGOUT_UBX_RXM_RAWX_USB",
        "CFG_MSGOUT_UBX_RXM_SFRBX_USB",
        #"CFG_MSGOUT_UBX_TIM_TM2_USB",
        #"CFG_MSGOUT_UBX_TIM_TP_USB",
    ]

    # enable what we want:
    enable = [(k, 1) for k in interest]
    for c in enable:
        valset(ser, c)
        time.sleep(0.05)
        print("[CFG] Sending enable for ", c)

    print("[CFG] Finished Config. All preferred UBX messages enabled")


if __name__ == "__main__":
    run_ubx_monitor()
    try:
        while True:
            try:
                ts, msg = rxq.get(timeout=1.0)
                #if printFlag == 0:
                #    pass
                #else:
                print(msg)
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
