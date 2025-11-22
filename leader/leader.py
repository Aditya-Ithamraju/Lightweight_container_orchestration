# leader/leader.py
from flask import Flask, request, jsonify, send_from_directory, Response
import os, time, threading, uuid, requests
from collections import deque
from scheduler import choose_node

app = Flask(__name__)

# ---------- config ----------
BASE_DIR = os.path.dirname(__file__)
PAYLOAD_DIR = os.path.join(BASE_DIR, "payloads")
NODE_STALE_SEC = 12          # after this, show "stale"
NODE_OFFLINE_SEC = 30        # after this, show "offline"
MAX_RECENT_TASKS = 50

# ---------- in-memory state ----------
nodes = {}  # node_id -> {node_id, caps, metrics, last_seen, status}
tasks = {}  # task_id -> {...}
recent_tasks = deque(maxlen=MAX_RECENT_TASKS)
last_broadcast_report = {"scheduled": [], "skipped": [], "status": "ok", "total": 0}
deployment_counter = {}  # Track deployments per node for round-robin
last_deployed_node_idx = 0  # For round-robin

LOCK = threading.Lock()

# ---------- helpers ----------
def now_s():
    return int(time.time())

def node_health(ns):
    """Return online/stale/offline without mutating input."""
    age = now_s() - int(ns.get("last_seen", 0))
    if age > NODE_OFFLINE_SEC:
        return "offline"
    if age > NODE_STALE_SEC:
        return "stale"
    return "online"

def _choose_nodes(selector):
    """Filter nodes using selector = {require_caps:{}, min_battery:int}"""
    selector = selector or {}
    require_caps = selector.get("require_caps", {})
    min_batt = int(selector.get("min_battery", 0))
    selected, skipped = [], []

    for nid, info in nodes.items():
        status = node_health(info)
        caps = info.get("caps", {}) or {}
        batt = int((info.get("metrics", {}) or {}).get("battery_pct", 0))

        if status != "online":
            skipped.append({"node_id": nid, "reason": status})
            continue

        ok_caps = True
        for k, v in require_caps.items():
            if bool(caps.get(k)) != bool(v):
                ok_caps = False
                break
        if not ok_caps:
            skipped.append({"node_id": nid, "reason": "caps_mismatch"})
            continue

        if batt < min_batt:
            skipped.append({"node_id": nid, "reason": "low_battery"})
            continue

        selected.append(nid)

    return selected, skipped

def _mk_task(node_id, code_url, config):
    tid = uuid.uuid4().hex[:10]
    t = {
        "task_id": tid,
        "node_id": node_id,
        "code_url": code_url,
        "config": config or {},
        "status": "queued",
        "error": "",
        "output": "",
        "queued_at": now_s(),
        "started_at": None,
        "finished_at": None,
        "updated_at": now_s(),
    }
    tasks[tid] = t
    recent_tasks.appendleft(t)
    return t

# ---------- endpoints: control plane ----------
@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    nid = data.get("node_id")
    if not nid:
        return jsonify({"error": "node_id required"}), 400
    with LOCK:
        prev = nodes.get(nid, {"node_id": nid, "caps": {}, "metrics": {}})
        prev["node_id"] = nid
        prev["addr"] = data.get("addr", prev.get("addr", ""))
        prev["caps"] = data.get("caps", prev.get("caps", {}))
        prev["metrics"] = data.get("metrics", prev.get("metrics", {}))
        prev["last_seen"] = now_s()
        prev["status"] = "online"  # UI recomputes real health
        nodes[nid] = prev
    return jsonify({"status": "ok"}), 200

@app.route("/nodes", methods=["GET"])
def list_nodes():
    with LOCK:
        out = {}
        for nid, info in nodes.items():
            d = dict(info)
            d["status"] = node_health(info)
            # Add deployment count from leader's tracking
            d["deployments"] = deployment_counter.get(nid, 0)
            out[nid] = d
        return jsonify(out)

@app.route("/deploy", methods=["POST"])
def deploy():
    """
    Deploy a container to the best available agent using round-robin with energy awareness.
    Request: {
        "image": "docker-image:tag",
        "name": "container-name",
        "port": 5000,
        "resources": {"cpu": 0.05, "mem_mb": 30, "min_energy": 10}
    }
    """
    global last_deployed_node_idx, deployment_counter
    
    body = request.json or {}
    image = body.get("image")
    name = body.get("name")
    port = body.get("port")
    resources = body.get("resources", {})
    
    if not image or not name:
        return jsonify({"error": "image and name required"}), 400
    
    with LOCK:
        # Get online nodes with metrics
        online_nodes = []
        for nid, info in nodes.items():
            if node_health(info) == "online":
                metrics = info.get("metrics", {})
                online_nodes.append({
                    "node_id": nid,
                    "free_cpu": metrics.get("free_cpu", 1.0),
                    "free_mem_mb": metrics.get("free_mem_mb", 1024),
                    "energy_pct": metrics.get("energy_pct", 100),
                    "addr": info.get("addr", ""),
                    "deployments": deployment_counter.get(nid, 0)
                })
        
        if not online_nodes:
            return jsonify({"error": "no agents available"}), 503
        
        # Sort by: fewest deployments, then highest energy, then most free resources
        online_nodes.sort(key=lambda n: (
            n["deployments"],  # Prefer nodes with fewer deployments
            -n["energy_pct"],   # Then higher energy
            -n["free_cpu"],     # Then more CPU
            -n["free_mem_mb"]   # Then more memory
        ))
        
        # Pick the first suitable node
        chosen_node_data = None
        for node_data in online_nodes:
            if (node_data["free_cpu"] >= resources.get("cpu", 0) and
                node_data["free_mem_mb"] >= resources.get("mem_mb", 0) and
                node_data["energy_pct"] >= resources.get("min_energy", 0)):
                chosen_node_data = node_data
                break
        
        if not chosen_node_data:
            return jsonify({"error": "no suitable agent found (resource constraints)"}), 503
        
        chosen_node = chosen_node_data["node_id"]
        agent_addr = chosen_node_data["addr"]
        
        if not agent_addr:
            return jsonify({"error": "agent address not found"}), 500
        
        # Track deployment
        deployment_counter[chosen_node] = deployment_counter.get(chosen_node, 0) + 1
    
    # Send deployment request to the chosen agent
    try:
        agent_url = f"http://{agent_addr}/run"
        payload = {
            "image": image,
            "name": name,
            "port": port
        }
        
        resp = requests.post(agent_url, json=payload, timeout=30)
        
        if resp.ok:
            return jsonify({
                "status": "success",
                "node": chosen_node,
                "agent_addr": agent_addr,
                "container_name": name,
                "message": f"Deployed to {chosen_node}",
                "total_on_node": deployment_counter.get(chosen_node, 0)
            }), 200
        else:
            # Rollback counter on failure
            with LOCK:
                deployment_counter[chosen_node] = max(0, deployment_counter.get(chosen_node, 1) - 1)
            return jsonify({
                "error": "agent deployment failed",
                "node": chosen_node,
                "agent_response": resp.text
            }), 500
            
    except requests.exceptions.RequestException as e:
        # Rollback counter on failure
        with LOCK:
            deployment_counter[chosen_node] = max(0, deployment_counter.get(chosen_node, 1) - 1)
        return jsonify({
            "error": "failed to contact agent",
            "node": chosen_node,
            "details": str(e)
        }), 500

@app.route("/task", methods=["GET"])
def fetch_task():
    """Agent long-polls with ?node_id=<id> to get next queued task."""
    nid = request.args.get("node_id")
    if not nid:
        return jsonify({"error": "node_id required"}), 400

    with LOCK:
        chosen = None
        for t in tasks.values():
            if t["node_id"] == nid and t["status"] == "queued":
                chosen = t
                break

        if not chosen:
            return jsonify({"task_id": None}), 200

        chosen["status"] = "running"
        chosen["started_at"] = now_s()
        chosen["updated_at"] = now_s()
        return jsonify({
            "task_id": chosen["task_id"],
            "code_url": chosen["code_url"],
            "config": chosen["config"]
        }), 200

@app.route("/result", methods=["POST"])
def submit_result():
    data = request.json or {}
    tid = data.get("task_id")
    if not tid or tid not in tasks:
        return jsonify({"error": "unknown_task"}), 404
    with LOCK:
        t = tasks[tid]
        t["status"] = data.get("status", "ok")
        t["output"] = data.get("output", "")
        t["error"] = data.get("error", "")
        t["finished_at"] = now_s()
        t["updated_at"] = now_s()
    return jsonify({"status": "ok"}), 200

@app.route("/results/<task_id>", methods=["GET"])
def get_result(task_id):
    with LOCK:
        t = tasks.get(task_id)
        if not t:
            return jsonify({"error": "not_found"}), 404
        return jsonify(t)

@app.route("/broadcast", methods=["POST"])
def broadcast():
    """
    {
      "selector": {"require_caps":{"led":true}, "min_battery":50},
      "code_url": "http://127.0.0.1:8000/payloads/task_print.py",
      "config": {"msg":"hi"}
    }
    """
    body = request.json or {}
    selector = body.get("selector", {})
    code_url = body.get("code_url")
    config = body.get("config", {})

    if not code_url:
        return jsonify({"error": "code_url required"}), 400

    with LOCK:
        selected, skipped = _choose_nodes(selector)
        scheduled = []
        for nid in selected:
            t = _mk_task(nid, code_url, config)
            scheduled.append({"node_id": nid, "task_id": t["task_id"]})

        global last_broadcast_report
        last_broadcast_report = {
            "status": "ok",
            "total": len(scheduled),
            "scheduled": scheduled,
            "skipped": skipped
        }

        return jsonify(last_broadcast_report), 200

# ---------- payload serving ----------
@app.route("/payloads/<path:fname>", methods=["GET"])
def get_payload(fname):
    full = os.path.join(PAYLOAD_DIR, fname)
    if not os.path.isfile(full):
        return Response("Not Found", 404)
    return send_from_directory(PAYLOAD_DIR, fname, as_attachment=False)

# ---------- dashboard + state ----------
@app.route("/api/state", methods=["GET"])
def api_state():
    with LOCK:
        node_list = []
        for nid, info in nodes.items():
            d = dict(info)
            d["status"] = node_health(info)
            node_list.append(d)
        return jsonify({
            "now": now_s(),
            "nodes": node_list,
            "recent_tasks": list(recent_tasks),
            "last_broadcast": last_broadcast_report
        })

@app.route("/dashboard", methods=["GET"])
def dashboard():
    # dependency-free UI (dark) that auto-refreshes /api/state
    html = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Edge Mini-K8s • Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {
  --bg:#0e1117; --panel:#161b22; --text:#e6edf3; --muted:#9da7b3;
  --ok:#1f6feb; --good:#2ea043; --bad:#f85149; --warn:#d29922;
  --chip:#30363d; --chip-text:#c9d1d9;
}
* { box-sizing:border-box; font-family: ui-sans-serif, system-ui, Segoe UI, Roboto, Arial; }
body { margin:0; background:var(--bg); color:var(--text); }
.wrap { max-width:1200px; margin:24px auto; padding:0 16px; }
h1 { font-size:20px; margin:0 0 12px; }
.grid { display:grid; gap:16px; grid-template-columns: 1fr 1fr; }
.card { background:var(--panel); border:1px solid #30363d; border-radius:12px; padding:16px; }
.small { color:var(--muted); font-size:12px; }
.table { width:100%; border-collapse:collapse; margin-top:8px; }
.table th, .table td { border-top:1px solid #30363d; padding:10px; text-align:left; font-size:14px; }
.chip { display:inline-block; padding:2px 8px; border-radius:999px; background:var(--chip); color:var(--chip-text); font-size:12px; }
.chip.ok { background:rgba(46,160,67,.15); color:#2ea043; }
.chip.err { background:rgba(248,81,73,.15); color:#f85149; }
.chip.warn { background:rgba(210,153,34,.15); color:#d29922; }
.kv { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:12px; color:var(--muted); }
.footer { color:var(--muted); font-size:12px; margin-top:10px; }
.badge { padding:2px 8px; border-radius:999px; font-size:12px; }
.badge.ok { background:rgba(46,160,67,.15); color:#2ea043; }
.badge.error { background:rgba(248,81,73,.15); color:#f85149; }
.badge.running { background:rgba(31,111,235,.15); color:#1f6feb; }
.badge.queued { background:rgba(210,153,34,.15); color:#d29922; }
.code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:12px; }
@media (max-width: 900px){ .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="wrap">
  <h1>Edge Mini-K8s • Dashboard</h1>
  <div class="small">Auto-refreshes every <b>3s</b></div>

  <div class="grid" style="margin-top:12px;">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <b>Nodes</b>
        <span id="ts" class="small"></span>
      </div>
      <table class="table" id="nodes">
        <thead><tr><th>ID</th><th>Status</th><th>Battery</th><th>Caps</th><th>Last Seen</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>

    <div class="card">
      <b>Recent Tasks</b>
      <table class="table" id="tasks">
        <thead><tr><th>Task</th><th>Node</th><th>Status</th><th>Queued</th><th>Finished</th></tr></thead>
        <tbody></tbody>
      </table>
      <div class="footer">Tip: payloads are served from <span class="code">/payloads</span>. Example:
        <span class="code">http://127.0.0.1:8000/payloads/task_print.py</span></div>
    </div>

    <div class="card" style="grid-column: 1 / -1;">
      <b>Last Broadcast</b>
      <div id="bc"></div>
    </div>
  </div>
</div>

<script>
function rel(secNow, ts){
  if (!ts) return "—";
  const d = secNow - ts;
  if (d < 2) return "just now";
  if (d < 60) return d + "s ago";
  if (d < 3600) return Math.floor(d/60) + "m ago";
  return Math.floor(d/3600) + "h ago";
}
function chipStatus(s){
  if(s==="online") return '<span class="chip ok">online</span>';
  if(s==="stale") return '<span class="chip warn">stale</span>';
  return '<span class="chip err">offline</span>';
}
function badge(s){
  const cls = (s==="ok")?"ok":(s==="running")?"running":(s==="queued")?"queued":"error";
  return '<span class="badge '+cls+'">'+s+'</span>';
}
async function load(){
  const r = await fetch('/api/state');
  const data = await r.json();
  document.getElementById('ts').innerText = new Date(data.now*1000).toLocaleString();

  // nodes
  const nbody = document.querySelector('#nodes tbody');
  nbody.innerHTML = '';
  (data.nodes || []).forEach(n=>{
    const caps = JSON.stringify(n.caps || {});
    const batt = (n.metrics && n.metrics.battery_pct!=null)? (n.metrics.battery_pct+'%') : '—';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="code">${n.node_id}</td>
      <td>${chipStatus(n.status)}</td>
      <td>${batt}</td>
      <td class="kv">${caps}</td>
      <td class="small">${rel(data.now, n.last_seen)}</td>`;
    nbody.appendChild(tr);
  });

  // tasks
  const tbody = document.querySelector('#tasks tbody');
  tbody.innerHTML = '';
  (data.recent_tasks || []).forEach(t=>{
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="code">${t.task_id}</td>
      <td class="code">${t.node_id}</td>
      <td>${badge(t.status)}</td>
      <td class="small">${t.queued_at? new Date(t.queued_at*1000).toLocaleTimeString() : '—'}</td>
      <td class="small">${t.finished_at? new Date(t.finished_at*1000).toLocaleTimeString() : '—'}</td>`;
    tbody.appendChild(tr);
  });

  // last broadcast report
  const bc = data.last_broadcast || {};
  const sched = (bc.scheduled||[]).map(s=>`<span class="code">${s.node_id}</span>`).join(', ') || '—';
  const skipped = (bc.skipped||[]).map(s=>`<span class="code">${s.node_id}</span> <span class="small">(${s.reason})</span>`).join(', ') || '—';
  const wrap = document.getElementById('bc');
  wrap.innerHTML = `
    <div class="small" style="margin-top:6px;">
      <b>Scheduled:</b> ${sched}
      <br/>
      <b>Skipped:</b> ${skipped}
    </div>`;
}
load();
setInterval(load, 3000);
</script>
</body>
</html>"""
    return Response(html, mimetype="text/html")

# ---------- background (placeholder for future housekeeping) ----------
def cleaner_loop():
    while True:
        time.sleep(5)
        # No mutation needed; UI computes status.

# ---------- main ----------
if __name__ == "__main__":
    os.makedirs(PAYLOAD_DIR, exist_ok=True)
    t = threading.Thread(target=cleaner_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=8000)
