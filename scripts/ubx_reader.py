import serial
import threading
import time
from pyubx2 import UBXReader, UBXMessage, SET, GET, POLL_LAYER_RAM, UBX_CONFIG_DATABASE
from riml.config_matrix import (
        empty_matrix,
        update_matrix,
        get_keywords,
        get_messages,
        get_ifaces,
        print_matrix_as_table,
        parse_cfg_key,
        )


PORT = "/dev/ttyACM0"
BAUD = 115200 #usb doesn't care about rate, but param needs to exist
snapshot_buffer = [] 
lock = threading.Lock()

ser = serial.Serial(PORT, BAUD, timeout=1)
ubr = UBXReader(ser, protfilter=2) #protfilter=2) to filter for ubx protocol messages


# receiver loop must always run otehrwise usb cdc stream can stall and become inaccessible to reading for some reason
def rx_loop():
    print("[RX] started")
    while True:
        try:
            raw, msg = ubr.read()
            if not msg:
                continue

            if msg.identity == "CFG-VALGET":
                print(msg)
                pass
                  
            else:
                #print(msg)
                pass

        except Exception as e:
            print("[RX ERROR] couldn't read messages, exiting receiver loop: ", e)
            break

# VALSET
def valset(key, value):
    msg = UBXMessage("CFG", "CFG-VALSET", SET, version=0, layers=1, reserved0=0, cfgData=(key, value))
    ser.write(msg.serialize())
    ser.flush()

# VALGET
def valget(keys):
    if isinstance(keys, str):
        keys = [keys]
    msg = UBXMessage.config_poll(POLL_LAYER_RAM, 0, keys)
    ser.write(msg.serialize())
    ser.flush()

# construct interesting keys based on messages and interfaces monitored in config state matrix
def build_interest_keys():
    msgs = set(get_messages())
    #ifaces = set(get_ifaces())
    ifaces = ["USB", "UART1"] #simplified for now - only usb interesting
    iface = "USB"

    keys = [
        k for k in UBX_CONFIG_DATABASE
        if k.startswith("CFG_MSGOUT")
        and ("NMEA" in k or "UBX" in k)
        and k.endswith(iface)
    ]
    return keys

def enable_some_UBX_messages(keys):
    for key in keys:
        valset(key, 1)

#########################################################
#########################################################
#runtime
t = threading.Thread(target=rx_loop, daemon=True) #boilerplate daemon mode thread with infinite loop function
t.start()
print("[GNSS RX] daemon running, <Ctrl+C> to exit")

#initial setup - enable UBX messages
keys = ['CFG_MSGOUT_UBX_MON_HW_USB', 'CFG_MSGOUT_UBX_MON_IO_USB', 'CFG_MSGOUT_UBX_MON_RF_USB', 'CFG_MSGOUT_UBX_NAV_DOP_USB', 'CFG_MSGOUT_UBX_NAV_POSECEF_USB', 'CFG_MSGOUT_UBX_NAV_PVT_USB', 'CFG_MSGOUT_UBX_NAV_SAT_USB', 'CFG_MSGOUT_UBX_NAV_STATUS_USB', 'CFG_MSGOUT_UBX_NAV_VELNED_USB', 'CFG_MSGOUT_UBX_RXM_RAWX_USB', 'CFG_MSGOUT_UBX_RXM_SFRBX_USB', 'CFG_MSGOUT_UBX_TIM_TM2_USB', 'CFG_MSGOUT_UBX_TIM_TP_USB']

try:
    config_state = empty_matrix()
    interest_keys = build_interest_keys()
    enable_some_UBX_messages(keys)
    #print(interest_keys)
    while True: #comment out to only poll once
        time.sleep(1.8)
        #valget(get_keywords())
        valget(keys)
        time.sleep(1)
        with lock:
            snapshot = dict(snapshot_buffer)
            snapshot_buffer.clear()

        config_state = update_matrix(snapshot, config_state)
        print_matrix_as_table(config_state)
except KeyboardInterrupt:
    print("[GNSS RX ENDED] Shutting down...")
    ser.close()
    print("Serial link closed")
