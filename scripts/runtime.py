import time
import queue

from rime.ubx_monitor import run_ubx_monitor, rxq, stop_evt
from rime.integrity_engine import UBXIntegrityEngine

def render(matrix, events, max_rows=40):
    # clear screen
    print("\033[2J\033[H", end="")

    print("=== SIGNAL STATE MATRIX ===\n")

    # header
    print("GNSS\tSV\tSNR\tEL\tRES\tUSErx\tHEALTH\tSEV\tPVT")

    for row in matrix[:max_rows]:
        print(
            f"{row['gnss']}\t"
            f"{row['sv_id']}\t"
            f"{row.get('snr','-')}\t"
            f"{row.get('elev','-')}\t"
            f"{row.get('prRes','-')}\t"
            f"{row.get('svUsed','-')}\t"
            f"{row.get('health','-')}\t"
            f"{row['severity']}\t"
            f"{int(row['include_in_pvt'])}"
        )

    print("\n=== EVENTS (tail) ===\n")

    for e in events[-10:]:
        print(f"{e['ts']:.3f}\t{e['label']}\t{e['event']}")

def main():
    engine = UBXIntegrityEngine(console_out=False)

    # start monitor (starts RX thread internally)
    run_ubx_monitor()

    print("[GLUE] running")

    try:
#        while not stop_evt.is_set():
#            try:
#                ts, msg = rxq.get(timeout=0.5)
#            except queue.Empty:
#                continue
#            #print(msg)
#            engine.ingest(ts, msg)
#
        last_render = 0
        
        while not stop_evt.is_set():
            try:
                ts, msg = rxq.get(timeout=0.1)
                engine.ingest(ts, msg)
            except queue.Empty:
                pass
        
            now = time.monotonic()
        
            # refresh UI at ~5 Hz
            if now - last_render > 0.2:
                snap = engine.snapshot()
                render(snap["matrix"], snap["events"])
                last_render = now
    
    except KeyboardInterrupt:
        print("[GLUE] stopping...")
        stop_evt.set()
        print("[GLUE] stop signal sent")
        time.sleep(1)


if __name__ == "__main__":
    main()
