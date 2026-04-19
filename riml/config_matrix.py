"""
generate a state space matrix for configuration of all outputs
of f9p taken in form: message x interface

provides functions for:
    -message/iface definition
    -state matrix creation
    -config key list generation
    -table rendering of config state space
"""


from tabulate import tabulate

def print_matrix_as_table(matrix):
    msgs = sorted(matrix.keys())
    ifaces = sorted(next(iter(matrix.values())).keys())

    table = []
    for msg in msgs:
        row = [msg] + [matrix[msg][iface] for iface in ifaces]
        table.append(row)

    print(tabulate(table, headers=["MSG"] + ifaces))

def parse_cfg_key(key, pream="CFG_MSGOUT"):
    """
    Splits a keyword such as "CFG-MSGOUT-UBX_NAV_PVT_USB" into interface (USB) and message (UBX_NAV_PVT)
    Raises:
        ValueError on invalid format or unknown msg or iface
    """
    if not key.startswith(pream + "_"): raise ValueError(f"Invalid key prefix: {key}")
    #body = key without prefix. body includes msg and iface
    body = key[len(pream) + 1:]
    parts = body.split("_")
    #check for possibly too short body:
    if len(parts) < 2: raise ValueError(f"Invalid key format (too short): {key}")
    
    iface = parts[-1]
    msg = "_".join(parts[:-1])
    if iface not in get_ifaces(): raise ValueError(f"Unknown interface '{iface}' in key: {key}")
    if msg not in get_messages(): raise ValueError(f"Unknown message '{msg}' in key: {key}")
    return msg, iface
    # some old implementations (_, means "throw out"; split("delim", 2) means split 2x at most; *msg_parts means a list of parts should be generated: 
    #_, _, rest = key.split("-", 2)
    #*msg_parts, iface = rest.split("_")

def construct_cfg_key(msg, iface, pream="CFG_MSGOUT"):
    """
    builds a ubx cfg keyword based on an optional preamble, msg type and iface
    Args:
        pream (string): default "CFG_MSGOUT" but can be supplied by user to construct different types
        msg (string): needs to match one from support message types, see get_messages()
        iface (string): needs to match one of the supported ifaces from get_ifaces()
    """
    if msg not in get_messages(): raise ValueError(f"Unknown message '{msg}'")
    if iface not in get_ifaces(): raise ValueError(f"Unknown interface '{iface}'")
    return f"{pream}_{msg}_{iface}"

def get_messages():
    """
    Returns the list of message types by default used by riml, can be extended by modifying the MESSAGES list
    """
    MESSAGES = [
        "UBX_NAV_PVT",
        "UBX_NAV_SAT",
        "UBX_NAV_DOP",
        "UBX_NAV_STATUS",
        "UBX_NAV_POSECEF",
        "UBX_NAV_VELNED",

        "UBX_RXM_RAWX",
        "UBX_RXM_SFRBX",

        "UBX_MON_IO",
        "UBX_MON_HW",
        "UBX_MON_RF",

        "UBX_TIM_TM2",
        "UBX_TIM_TP",

        "NMEA_GGA",
        "NMEA_GLL",
        "NMEA_GSA",
        "NMEA_GSV",
        "NMEA_RMC",
        "NMEA_VTG",
        "NMEA_ZDA",
    ]
    return MESSAGES

def get_ifaces():
    """
    Returns the list of default interfaces used by riml, can be extended by modifying INTERFACES list
    """
    INTERFACES = [
        "USB",
        "UART1",
        "UART2",
    ]
    return INTERFACES

def empty_matrix():
    """
    Returns the initial empty state space representation of the config
    """
    return {
        msg: {iface: 0 for iface in get_ifaces()}
        for msg in get_messages()
    }

def update_matrix(snapshot, matrix):
    """
    Update and return the state matrix using a snapshot of UBX config values (dict)

    Args:
        matrix (dict): nested dict representing the config state
        snapshot (dict): {"CFG-MSGOUT-...": value 0 or 1}

    Returns:
        dict: updated matrix representing config state of receiver
    """
    for key, value in snapshot.items():
        try:
            msg, iface = parse_cfg_key(key)
            if msg in matrix and iface in matrix[msg]:
                matrix[msg][iface] = value
            else:
                print(f"[WARN] {msg} / {iface} value cannot be updated in the config state matrix due to unknown mapping. Either {msg} doesnt exist in defined messages or {iface} is not in defined ifaces.")
        except Exception as e:
            print(f"[ERROR] Failed to parse key {key}: {e}")
    return matrix

def get_keywords():
    """
    generates a list of ubx cfg keywords based on MESSAGES and INTERFACES lists
    """
    return [
        construct_cfg_key(msg, iface)
        for msg in get_messages()
        for iface in get_ifaces()
    ]


if __name__ == "__main__":
    print("Tests:")
    print("Messages: ", get_messages())
    print()
    print("Interfaces: ", get_ifaces())
    print()
    print("Keywords list: ", get_keywords())
    print()
    print("Empty state matrix: ")
    print_matrix_as_table(empty_matrix())
    print()
    print("test parse_cfg_key CFG_MSGOUT_UBX_NAV_PVT_USB:  ", parse_cfg_key("CFG_MSGOUT_UBX_NAV_PVT_USB"))
    print() 
    print("test updating state matrix: ")
    print_matrix_as_table(update_matrix({"CFG_MSGOUT_UBX_NAV_PVT_USB": 1, "CFG_MSGOUT_UBX_NAV_POSECEF_USB": 1}, empty_matrix()))

