# agent/agent.py
from flask import Flask, request, jsonify
import threading, time, requests, os, subprocess, socket, uuid, psutil, shutil
MOVIES_DIR = os.path.join(os.path.dirname(__file__), "movies")

# Create folder and a few dummy files if not exist
os.makedirs(MOVIES_DIR, exist_ok=True)
sample_movies = ["inception.jpg", "batman.jpg", "avatar.jpg"]
for name in sample_movies:
    path = os.path.join(MOVIES_DIR, name)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(b"This is a mock movie file for " + name.encode())

app = Flask(__name__)

# --- Config via env ---
LEADER_ADDR = os.environ.get("LEADER_ADDR", "127.0.0.1:8000")
AGENT_PORT  = int(os.environ.get("AGENT_PORT", 9000))
NODE_ID     = os.environ.get("NODE_ID", f"node-{uuid.uuid4().hex[:6]}")
SIM_ENERGY  = int(os.environ.get("SIM_ENERGY", 100))  # 0–100%
ADVERTISE_HOST = os.environ.get("ADVERTISE_HOST")  # optional for same-laptop multi-agent

# --- Helpers ---
def get_ip():
    """Return the IP address this agent should advertise to the leader."""
    if ADVERTISE_HOST:
        return ADVERTISE_HOST
    return "127.0.0.1"  # default loopback for local runs

def local_metrics():
    """Return basic system metrics to help the leader schedule work.
    
    In a real edge deployment, each agent would be on separate hardware.
    For local simulation, we add variation to demonstrate heterogeneous resources.
    """
    import hashlib
    import random
    
    # Seed random with NODE_ID for consistent but varied behavior per agent
    node_hash = int(hashlib.md5(NODE_ID.encode()).hexdigest()[:8], 16)
    random.seed(node_hash + int(time.time() / 10))  # Changes every 10 seconds
    
    # Get base system metrics
    base_cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    base_mem_available_mb = int(mem.available / 1024 / 1024)
    
    # SIMULATED CPU: Add per-agent workload patterns
    # Lower energy agents simulate higher baseline load
    energy_factor = (100 - SIM_ENERGY) / 100.0  # 0.0 to 1.0
    cpu_baseline = energy_factor * 40  # 0-40% based on energy
    
    # Add time-varying component (simulates workload fluctuation)
    time_variation = random.uniform(-15, 15)
    
    # Add agent-specific offset
    agent_offset = (node_hash % 30) - 15  # -15 to +15
    
    cpu_pct = base_cpu * 0.3 + cpu_baseline + time_variation + agent_offset
    cpu_pct = min(100, max(5, cpu_pct))  # Clamp to 5-100%
    free_cpu = max(0.0, (100.0 - cpu_pct) / 100.0)
    
    # SIMULATED MEMORY: Each agent has "virtual" memory capacity
    # Simulate different memory sizes per agent
    agent_mem_total_mb = 8000 - (node_hash % 4) * 1500  # 2000-8000 MB range
    
    # Base usage percentage varies by agent
    mem_usage_pct = 40 + (node_hash % 40)  # 40-80% usage
    
    # Add fluctuation over time
    mem_usage_pct += random.uniform(-10, 10)
    mem_usage_pct = min(95, max(20, mem_usage_pct))
    
    # Calculate free memory from simulated total and usage
    free_mem_mb = int(agent_mem_total_mb * (1 - mem_usage_pct / 100.0))
    
    return {
        "cpu_pct": round(cpu_pct, 1),
        "free_cpu": round(free_cpu, 3),
        "free_mem_mb": free_mem_mb,
        "energy_pct": SIM_ENERGY,
        "mem_total_mb": agent_mem_total_mb,  # For GUI to use correct total
    }

def run_cmd(args, timeout=60):
    """Run a subprocess and capture its output."""
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)

# --- Control-plane registration (heartbeat) ---
def heartbeat_loop():
    """Send periodic node registration updates to the leader."""
    while True:
        try:
            metrics = local_metrics()
            payload = {
                "node_id": NODE_ID, 
                "addr": f"{get_ip()}:{AGENT_PORT}",
                "metrics": metrics
            }
            requests.post(f"http://{LEADER_ADDR}/register", json=payload, timeout=3)
        except Exception as e:
            print("heartbeat error:", e)
        time.sleep(8)

# --- Data-plane: container control ---
@app.route("/run", methods=["POST"])
def run_container():
    """
    JSON payload example:
      {
        "image": "krishna2530/mini-test-app:latest",
        "name": "demo-app",
        "port": 5050,             # host port
        "container_port": 5000    # optional, default 5000
      }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"error": "bad_request", "detail": "invalid JSON"}), 400

    image = data.get("image")
    name = data.get("name")
    host_port = int(data.get("port", 5000))
    container_port = int(data.get("container_port", 5000))

    if not image or not name:
        return jsonify({"error": "bad_request", "detail": "image and name required"}), 400

    # Ensure docker is available
    docker_path = shutil.which("docker")
    if not docker_path:
        return jsonify({
            "error": "docker_not_found",
            "detail": "Docker CLI not found in PATH"
        }), 500

    # Pull image
    pull = run_cmd([docker_path, "pull", image], timeout=180)
    if pull.returncode != 0:
        return jsonify({
            "error": "docker_pull_failed",
            "stdout": pull.stdout,
            "stderr": pull.stderr
        }), 500

    # Run container
    runargs = [
        docker_path, "run", "-d", "--rm",
        "--name", name,
        "-p", f"{host_port}:{container_port}",
        image
    ]
    runres = run_cmd(runargs, timeout=120)
    if runres.returncode != 0:
        return jsonify({
            "error": "docker_run_failed",
            "stdout": runres.stdout,
            "stderr": runres.stderr
        }), 500

    cid = (runres.stdout or "").strip()
    return jsonify({"status": "ok", "runtime": "docker", "container_id": cid}), 200

# --- List containers ---
@app.route("/containers", methods=["GET"])
def list_containers():
    """Return all running containers on this agent."""
    docker_path = shutil.which("docker")
    if not docker_path:
        return jsonify({"error": "docker_not_found"}), 500
    try:
        res = run_cmd([docker_path, "ps", "--format", "{{.Names}}|{{.Image}}|{{.Ports}}"], timeout=15)
        containers = []
        for line in res.stdout.splitlines():
            parts = line.split("|", 2)
            if len(parts) >= 3:
                name, image, ports = parts
            elif len(parts) == 2:
                name, image = parts
                ports = ""
            else:
                continue
            containers.append({"name": name.strip(), "image": image.strip(), "ports": ports.strip()})
        return jsonify(containers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Stop container ---
@app.route("/stop", methods=["POST"])
def stop_container():
    """Stop and remove a running container by name."""
    try:
        data = request.get_json(force=True)
        name = data.get("name")
    except Exception:
        return jsonify({"error": "bad_request"}), 400

    if not name:
        return jsonify({"error": "name required"}), 400

    docker_path = shutil.which("docker")
    if not docker_path:
        return jsonify({"error": "docker_not_found"}), 500

    res = run_cmd([docker_path, "rm", "-f", name], timeout=15)
    if res.returncode == 0:
        return jsonify({"status": "stopped", "name": name})
    else:
        return jsonify({"error": res.stderr}), 500

# --- Metrics ---
@app.route("/metrics", methods=["GET"])
def metrics():
    """Return live CPU, memory, and energy metrics."""
    m = local_metrics()
    m["node_id"] = NODE_ID
    m["last_seen"] = int(time.time())
    return jsonify(m)
from flask import send_from_directory

@app.route("/list", methods=["GET"])
def list_movies():
    """List available movie files on this agent."""
    files = [f for f in os.listdir(MOVIES_DIR) if os.path.isfile(os.path.join(MOVIES_DIR, f))]
    return jsonify({"node_id": NODE_ID, "movies": files})

@app.route("/movie/<name>", methods=["GET"])
def get_movie(name):
    """Serve a movie (mock file) from this agent."""
    filepath = os.path.join(MOVIES_DIR, name)
    if not os.path.exists(filepath):
        return jsonify({"error": "movie_not_found"}), 404
    return send_from_directory(MOVIES_DIR, name)

# --- MAIN ENTRY ---
if __name__ == "__main__":
    print(f"Starting Agent {NODE_ID} on port {AGENT_PORT}, leader={LEADER_ADDR}")
    th = threading.Thread(target=heartbeat_loop, daemon=True)
    th.start()
    app.run(host="0.0.0.0", port=AGENT_PORT)