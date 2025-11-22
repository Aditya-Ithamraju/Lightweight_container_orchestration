# mcu/payloads/task_blink.py
import os, json, time

def main(config):
    cycles = int(config.get("cycles", 3))
    interval_ms = int(config.get("interval_ms", 300))
    pin = config.get("pin", "LED1")

    for i in range(1, cycles + 1):
        print(f"[LED:{pin}] ON  (#{i})")
        time.sleep(interval_ms / 1000.0)
        print(f"[LED:{pin}] OFF (#{i})")
        time.sleep(interval_ms / 1000.0)

    print(f"[LED:{pin}] done {cycles} cycles")

if __name__ == "__main__":
    raw = os.getenv("TASK_CONFIG") or os.getenv("TASK_CONFIG_JSON") or "{}"
    try:
        cfg = json.loads(raw)
    except Exception:
        cfg = {}
    main(cfg)
