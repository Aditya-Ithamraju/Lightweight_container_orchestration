# task_blink.py  (safe, self-contained)
import time

def main(config):
    # defaults + type safety
    try:
        cycles = int(config.get("cycles", 3))
    except Exception:
        cycles = 3
    try:
        interval_ms = int(config.get("interval_ms", 300))
    except Exception:
        interval_ms = 300
    pin = str(config.get("pin", "LED1"))

    # basic validation
    cycles = max(1, min(cycles, 20))         # 1..20
    interval_s = max(0.05, interval_ms/1000) # >=50ms

    out_lines = []
    for i in range(1, cycles+1):
        msg_on  = f"[LED:{pin}] ON  (#{i})"
        msg_off = f"[LED:{pin}] OFF (#{i})"
        print(msg_on);  out_lines.append(msg_on)
        time.sleep(interval_s)
        print(msg_off); out_lines.append(msg_off)
        time.sleep(interval_s)

    done = f"[LED:{pin}] done {cycles} cycles"
    print(done); out_lines.append(done)
    # return a compact summary string (leader will store in /results)
    return "\n".join(out_lines)
