# leader/payloads/task_temp.py
import json, time, random

def main(config):
    out = {
        "location": config.get("location", "unknown"),
        "temp_c": round(22 + random.random()*6, 1),
        "humidity_pct": round(45 + random.random()*20, 1),
        "ts": int(time.time()),
    }
    print(json.dumps(out))
