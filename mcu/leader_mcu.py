# mcu/leader_mcu.py
import os, time, uuid
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# --- in-memory state ---
REGISTRY = {}         # node_id -> {caps: {}, metrics: {}, last_seen: ts}
PENDING  = {}         # node_id -> [task, ...]
RESULTS  = {}         # task_id -> {node_id, status, output, ts}

POLL_INTERVAL_S = int(os.environ.get("MCU_POLL_S", "3"))

# ---------- helpers ----------
def ensure_queue(node_id):
    if node_id not in PENDING:
        PENDING[node_id] = []

def node_matches(node_id, selector: dict) -> bool:
    info = REGISTRY.get(node_id, {})
    caps = info.get("caps", {}) or {}
    metrics = info.get("metrics", {}) or {}

    # explicit node list
    ids = selector.get("node_ids")
    if ids is not None and node_id not in ids:
        return False

    # require caps to match exact truthy/falsey values
    req_caps = selector.get("require_caps", {}) or {}
    for k, v in req_caps.items():
        if caps.get(k) != v:
            return False

    # minimum battery level
    min_batt = selector.get("min_battery")
    if min_batt is not None:
        if metrics.get("battery_pct", 0) < int(min_batt):
            return False

    return True

def make_task(code=None, code_url=None, config=None):
    if not code and not code_url:
        return None
    return {
        "type": "run",
        "task_id": uuid.uuid4().hex[:10],
        "code": code,
        "code_url": code_url,
        "config": config or {},
    }

# ---------- endpoints ----------
@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    node_id  = data.get("node_id", "unknown")
    metrics  = data.get("metrics", {}) or {}
    caps     = data.get("caps", {}) or {}

    REGISTRY[node_id] = {
        "metrics": metrics,
        "caps": caps,
        "last_seen": time.time(),
    }
    ensure_queue(node_id)
    return jsonify({"status": "ok", "interval_s": POLL_INTERVAL_S})

@app.route("/task", methods=["GET"])
def task():
    node_id = request.args.get("node_id")
    if not node_id:
        return jsonify({"error": "node_id required"}), 400
    ensure_queue(node_id)
    if PENDING[node_id]:
        return jsonify(PENDING[node_id].pop(0))
    return jsonify({"type": "noop"})

@app.route("/push_task", methods=["POST"])
def push_task():
    data = request.json or {}
    node_id = data.get("node_id")
    if not node_id:
        return jsonify({"error": "node_id required"}), 400
    t = make_task(code=data.get("code"),
                  code_url=data.get("code_url"),
                  config=data.get("config"))
    if not t:
        return jsonify({"error": "need code or code_url"}), 400
    ensure_queue(node_id)
    PENDING[node_id].append(t)
    return jsonify({"status": "queued", "node": node_id, "task_id": t["task_id"]})

@app.route("/broadcast", methods=["POST"])
def broadcast():
    """
    Body:
    {
      "code": "def main(cfg): print('hi')",   # or
      "code_url": "http://.../task.py",
      "config": {...},
      "selector": {
         "node_ids": ["mcu-1","mcu-2"],      # optional
         "require_caps": {"led": true},      # optional
         "min_battery": 50                   # optional
      }
    }
    """
    data = request.json or {}
    selector = data.get("selector", {}) or {}
    t = make_task(code=data.get("code"),
                  code_url=data.get("code_url"),
                  config=data.get("config"))
    if not t:
        return jsonify({"error": "need code or code_url"}), 400

    scheduled, skipped = [], []
    for node_id in list(REGISTRY.keys()):
        if node_matches(node_id, selector):
            # clone task with a unique id per node
            t2 = dict(t)
            t2["task_id"] = uuid.uuid4().hex[:10]
            ensure_queue(node_id)
            PENDING[node_id].append(t2)
            scheduled.append({"node_id": node_id, "task_id": t2["task_id"]})
        else:
            skipped.append({"node_id": node_id, "reason": "selector_mismatch"})

    return jsonify({"status": "ok",
                    "scheduled": scheduled,
                    "skipped": skipped,
                    "total": len(scheduled)})

@app.route("/result", methods=["POST"])
def result():
    data = request.json or {}
    tid   = data.get("task_id")
    if not tid:
        return jsonify({"error": "task_id required"}), 400
    RESULTS[tid] = {
        "node_id": data.get("node_id"),
        "status":  data.get("status"),
        "output":  data.get("output", ""),
        "ts": time.time(),
    }
    return jsonify({"status": "accepted"})

@app.route("/results/<task_id>", methods=["GET"])
def get_result(task_id):
    r = RESULTS.get(task_id)
    if not r:
        return jsonify({"error": "not_found"}), 404
    return jsonify(r)

@app.route("/nodes", methods=["GET"])
def nodes():
    out = {}
    for nid, info in REGISTRY.items():
        out[nid] = {
            "caps": info.get("caps", {}),
            "metrics": info.get("metrics", {}),
            "last_seen": info.get("last_seen"),
        }
    return jsonify(out)

# serve example payloads (e.g., mcu/payloads/task_print.py)
@app.route("/payloads/<path:fname>")
def payloads(fname):
    base = os.path.join(os.path.dirname(__file__), "payloads")
    return send_from_directory(base, fname)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
