# mcu/agent_micro_sim.py
import os, time, json, random, requests, traceback

LEADER = os.environ.get("LEADER_ADDR", "127.0.0.1:8000")
NODE_ID = os.environ.get("NODE_ID", "mcu-1")
CAP_LED = os.environ.get("CAP_LED", "true").lower() == "true"
CAP_TEMP = os.environ.get("CAP_TEMP", "true").lower() == "true"

def metrics():
    return {
        "battery_pct": 80,
        "free_mem_kb": random.randint(320000, 360000)
    }

def register(session):
    payload = {
        "node_id": NODE_ID,
        "caps": {"led": CAP_LED, "sensor": CAP_TEMP},
        "metrics": metrics()
    }
    r = session.post(f"http://{LEADER}/register", json=payload, timeout=3)
    r.raise_for_status()

def fetch_task(session):
    r = session.get(f"http://{LEADER}/task", params={"node_id": NODE_ID}, timeout=3)
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except Exception:
        return None

def post_result(session, res):
    session.post(f"http://{LEADER}/result", json=res, timeout=3)

def run_task(task):
    code_url = task.get("code_url")
    config = task.get("config") or {}
    task_id = task.get("task_id")
    out, err = "", ""

    try:
        resp = requests.get(code_url, timeout=6)
        resp.raise_for_status()
        ns = {}
        exec(resp.text, ns, ns)
        fn = ns.get("main")
        if callable(fn):
            ret = fn(config)
            if ret:
                out = str(ret)
        else:
            out = "[TASK] No main(config) found; nothing to do."
    except Exception as e:
        err = f"{e}\n{traceback.format_exc()}"

    return {
        "task_id": task_id,
        "node_id": NODE_ID,
        "output": out,
        "error": err
    }

def main():
    s = requests.Session()
    print(f"[{NODE_ID}] starting; leader http://{LEADER}")

    hb = 0
    while True:
        # ---- heartbeat: update last_seen every loop ----
        try:
            register(s)
            if hb % 20 == 0:
                print(f"[{NODE_ID}] heartbeat → /register")
            hb += 1
        except Exception as e:
            print(f"[{NODE_ID}] register error: {e}")

        # ---- pull & execute one task if present ----
        try:
            task = fetch_task(s)
            if task and task.get("task_id") and task.get("code_url"):
                print(f"[{NODE_ID}] received task {task['task_id']}")
                res = run_task(task)
                post_result(s, res)
                status = "ok" if not res["error"] else "error"
                print(f"[{NODE_ID}] task {task['task_id']} => {status}")
        except Exception as e:
            print(f"[{NODE_ID}] task fetch error: {e}")

        time.sleep(3)

if __name__ == "__main__":
    main()
