import os, sys, subprocess, threading, queue, time, json, shutil, webbrowser, socket
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
from datetime import datetime
from collections import deque, defaultdict

import requests

# For plotting
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

# --------- Project paths (relative to this file) ----------
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
LEADER_DIR = os.path.join(BASE_DIR, "leader")
AGENT_DIR  = os.path.join(BASE_DIR, "agent")

LEADER_PY  = os.path.join(LEADER_DIR, "leader.py")
AGENT_PY   = os.path.join(AGENT_DIR, "agent.py")

LEADER_ENV = os.path.join(LEADER_DIR, ".venv", "Scripts", "python.exe")
AGENT_ENV  = os.path.join(AGENT_DIR,  ".venv", "Scripts", "python.exe")

DOCKER_BIN = r"C:\Program Files\Docker\Docker\resources\bin"  # typical path

LEADER_URL = "http://127.0.0.1:8000"

# Support multiple agents
MAX_AGENTS = 4
AGENT_BASE_PORT = 9000

# --------- Small helpers ----------
def path_exists(p): 
    try: return os.path.exists(p)
    except: return False

def ensure_venv(venv_py_path, work_dir, requirements_txt="requirements.txt", log=lambda *_: None):
    """Create venv if missing; pip install -r requirements.txt (idempotent)."""
    scripts_dir = os.path.dirname(venv_py_path)
    venv_dir    = os.path.dirname(scripts_dir)
    if not path_exists(venv_py_path):
        log(f"[venv] Creating venv in: {venv_dir}")
        subprocess.check_call([sys.executable, "-m", "venv", venv_dir], cwd=work_dir)
    # install requirements
    req_path = os.path.join(work_dir, requirements_txt)
    if path_exists(req_path):
        log(f"[venv] Installing requirements in {work_dir} ...")
        subprocess.check_call([venv_py_path, "-m", "pip", "install", "--upgrade", "pip"], cwd=work_dir)
        subprocess.check_call([venv_py_path, "-m", "pip", "install", "-r", req_path], cwd=work_dir)
    else:
        log(f"[venv] No {requirements_txt} found in {work_dir}, skipping.")

def which_docker():
    # Prefer PATH; else append default Docker bin
    p = shutil.which("docker")
    if p: return p
    if path_exists(DOCKER_BIN):
        os.environ["PATH"] = DOCKER_BIN + os.pathsep + os.environ.get("PATH","")
        return shutil.which("docker")
    return None

def open_url(url):
    try:
        webbrowser.open(url)
    except Exception:
        pass

def find_free_port(start_port, max_tries=100):
    """Find a free TCP port on localhost, starting at start_port.
    Returns the first available port or start_port if none found within range.
    """
    port = int(start_port)
    for _ in range(max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                # Success means it's currently free; don't listen, just return
                return port
            except OSError:
                port += 1
    return int(start_port)

# --------- Background process wrapper ----------
class Proc:
    def __init__(self, name, cmd, cwd=None, env=None, log=lambda *_: None):
        self.name = name
        self.cmd  = cmd
        self.cwd  = cwd
        self.env  = env or os.environ.copy()
        self.log  = log
        self.p    = None
        self._th  = None

    def start(self):
        if self.p and self.p.poll() is None:
            self.log(f"[{self.name}] already running (pid={self.p.pid})")
            return
        self.log(f"[{self.name}] starting: {' '.join(self.cmd)}")
        # creationflags to avoid console pop-ups
        self.p = subprocess.Popen(
            self.cmd,
            cwd=self.cwd,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        self._th = threading.Thread(target=self._pump, daemon=True)
        self._th.start()

    def _pump(self):
        try:
            for line in self.p.stdout:
                self.log(f"[{self.name}] {line.rstrip()}")
        except Exception as e:
            self.log(f"[{self.name}] log error: {e}")

    def stop(self):
        if self.p and self.p.poll() is None:
            self.log(f"[{self.name}] stopping (pid={self.p.pid})")
            try:
                # On Windows, try taskkill first for Flask processes
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.p.pid)], 
                                 capture_output=True, timeout=5)
                    time.sleep(0.5)
                else:
                    self.p.terminate()
                    try:
                        self.p.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.p.kill()
                
                # Double-check if still running
                if self.p.poll() is None:
                    self.p.kill()
                    self.p.wait(timeout=2)
                
                self.log(f"[{self.name}] stopped successfully")
            except Exception as e:
                self.log(f"[{self.name}] stop error: {e}, forcing kill...")
                try:
                    self.p.kill()
                except:
                    pass
        else:
            self.log(f"[{self.name}] not running")

    def is_running(self):
        return self.p is not None and self.p.poll() is None

# --------- Metrics Data Store ----------
class MetricsStore:
    """Store time-series metrics for plotting"""
    def __init__(self, max_points=60):
        self.max_points = max_points
        self.timestamps = deque(maxlen=max_points)
        self.agent_cpu = defaultdict(lambda: deque(maxlen=max_points))
        self.agent_mem = defaultdict(lambda: deque(maxlen=max_points))
        self.agent_energy = defaultdict(lambda: deque(maxlen=max_points))
        self.agent_containers = defaultdict(lambda: deque(maxlen=max_points))
        self.total_deployments = 0
        
    def add_snapshot(self, nodes_data):
        """Add a new snapshot of metrics"""
        now = datetime.now()
        self.timestamps.append(now)
        
        for node_id, info in nodes_data.items():
            # Get metrics from nested dict
            metrics = info.get("metrics", {})
            cpu_pct = metrics.get("cpu_pct", 0)
            free_mem_mb = metrics.get("free_mem_mb", 1564)
            energy = metrics.get("energy_pct", 100)
            mem_total_mb = metrics.get("mem_total_mb", 8000)  # Agent-specific total
            
            # Calculate actual usage percentages
            cpu_usage = cpu_pct  # Already a percentage
            mem_used_mb = max(0, mem_total_mb - free_mem_mb)
            mem_usage = (mem_used_mb / mem_total_mb) * 100 if mem_total_mb > 0 else 0
            mem_usage = max(0, min(100, mem_usage))  # Clamp to 0-100%
            
            self.agent_cpu[node_id].append(cpu_usage)
            self.agent_mem[node_id].append(mem_usage)
            self.agent_energy[node_id].append(energy)
            
    def add_container_count(self, node_id, count):
        """Track container distribution"""
        self.agent_containers[node_id].append(count)
        
    def get_workload_distribution(self):
        """Get current workload distribution across agents"""
        distribution = {}
        for node_id, counts in self.agent_containers.items():
            if counts:
                distribution[node_id] = counts[-1]
        return distribution

# --------- Tk App ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Edge Mini K8s - Advanced Orchestrator GUI with Analytics")
        self.geometry("1600x900")

        self.queue = queue.Queue()
        self.after(80, self._drain_queue)

        # Metrics store
        self.metrics = MetricsStore()

        # Notebook
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        # Tabs
        self.tab_ctrl  = ttk.Frame(nb)
        self.tab_plots = ttk.Frame(nb)
        self.tab_lead  = ttk.Frame(nb)
        self.tab_agent = ttk.Frame(nb)
        nb.add(self.tab_ctrl, text="Controls & Status")
        nb.add(self.tab_plots, text="📊 Analytics & Plots")
        nb.add(self.tab_lead, text="Leader Logs")
        nb.add(self.tab_agent, text="Agent Logs")

        # Logs
        self.leader_log = ScrolledText(self.tab_lead, height=30)
        self.agent_log  = ScrolledText(self.tab_agent, height=30)
        self.leader_log.pack(fill="both", expand=True, padx=8, pady=8)
        self.agent_log.pack(fill="both", expand=True, padx=8, pady=8)

        # Controls layout
        self._build_controls(self.tab_ctrl)
        
        # Plots layout
        self._build_plots(self.tab_plots)

        # Processes
        self.leader_proc = None
        self.agent_procs = []  # List of agent processes
        
        # Start metrics collection
        self.after(3000, self._collect_metrics)

    def _log_leader(self, *msg):
        self.queue.put(("leader", " ".join(str(m) for m in msg)))

    def _log_agent(self, *msg):
        self.queue.put(("agent", " ".join(str(m) for m in msg)))

    def _drain_queue(self):
        try:
            while True:
                who, line = self.queue.get_nowait()
                if who == "leader":
                    self.leader_log.insert("end", line + "\n")
                    self.leader_log.see("end")
                else:
                    self.agent_log.insert("end", line + "\n")
                    self.agent_log.see("end")
        except queue.Empty:
            pass
        self.after(80, self._drain_queue)

    def _build_controls(self, parent):
        pad = {"padx": 6, "pady": 6}

        frm_top = ttk.LabelFrame(parent, text="Environment")
        frm_top.pack(fill="x", **pad)

        self.var_image = tk.StringVar(value="krishna2530/mini-test-app:latest")
        self.var_name  = tk.StringVar(value="demo-app")
        self.var_port  = tk.IntVar(value=5056)

        ttk.Label(frm_top, text="Image:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm_top, textvariable=self.var_image, width=42).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(frm_top, text="Name:").grid(row=0, column=2, sticky="w", **pad)
        ttk.Entry(frm_top, textvariable=self.var_name, width=24).grid(row=0, column=3, sticky="w", **pad)
        ttk.Label(frm_top, text="Port:").grid(row=0, column=4, sticky="w", **pad)
        ttk.Entry(frm_top, textvariable=self.var_port, width=10).grid(row=0, column=5, sticky="w", **pad)

        # Buttons row
        frm_btns = ttk.LabelFrame(parent, text="Actions")
        frm_btns.pack(fill="x", **pad)

        ttk.Button(frm_btns, text="Create/Check venvs", command=self.on_make_venvs).grid(row=0, column=0, **pad)
        ttk.Button(frm_btns, text="Start Leader", command=self.on_start_leader).grid(row=0, column=1, **pad)
        ttk.Button(frm_btns, text="Stop Leader",  command=self.on_stop_leader).grid(row=0, column=2, **pad)

        # Multi-agent controls
        ttk.Label(frm_btns, text="Agents:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Button(frm_btns, text="Start Agent 1", command=lambda: self.on_start_agent(0)).grid(row=1, column=1, **pad)
        ttk.Button(frm_btns, text="Start Agent 2", command=lambda: self.on_start_agent(1)).grid(row=1, column=2, **pad)
        ttk.Button(frm_btns, text="Start Agent 3", command=lambda: self.on_start_agent(2)).grid(row=1, column=3, **pad)
        ttk.Button(frm_btns, text="Start Agent 4", command=lambda: self.on_start_agent(3)).grid(row=1, column=4, **pad)
        
        ttk.Button(frm_btns, text="Start ALL Agents", command=self.on_start_all_agents).grid(row=2, column=1, **pad)
        ttk.Button(frm_btns, text="Stop ALL Agents",  command=self.on_stop_all_agents).grid(row=2, column=2, **pad)
        ttk.Button(frm_btns, text="🔥 FORCE KILL ALL", command=self.on_force_kill_all).grid(row=2, column=3, **pad)

        ttk.Separator(frm_btns, orient="horizontal").grid(row=3, column=0, columnspan=6, sticky="ew", **pad)

        ttk.Button(frm_btns, text="Deploy 1 App", command=self.on_deploy_leader).grid(row=4, column=0, **pad)
        ttk.Button(frm_btns, text="Deploy 5 Apps", command=lambda: self.on_deploy_multiple(5)).grid(row=4, column=1, **pad)
        ttk.Button(frm_btns, text="Deploy 10 Apps", command=lambda: self.on_deploy_multiple(10)).grid(row=4, column=2, **pad)
        ttk.Button(frm_btns, text="Open App URL",     command=self.on_open_app).grid(row=4, column=3, **pad)

        ttk.Button(frm_btns, text="GET /nodes",       command=self.on_get_nodes).grid(row=5, column=0, **pad)
        ttk.Button(frm_btns, text="docker ps (list)", command=self.on_docker_ps).grid(row=5, column=1, **pad)
        ttk.Button(frm_btns, text="Cleanup All",     command=self.on_cleanup).grid(row=5, column=2, **pad)

        # Agent Status Table
        frm_status = ttk.LabelFrame(parent, text="Agent Status")
        frm_status.pack(fill="both", expand=True, **pad)
        
        cols = ("Node ID", "Port", "Status", "CPU %", "Memory %", "Energy %", "Containers")
        self.agent_tree = ttk.Treeview(frm_status, columns=cols, show="headings", height=5)
        for col in cols:
            self.agent_tree.heading(col, text=col)
            self.agent_tree.column(col, width=120)
        self.agent_tree.pack(fill="both", expand=True, **pad)
        
        # Scrollbar for tree
        vsb = ttk.Scrollbar(frm_status, orient="vertical", command=self.agent_tree.yview)
        vsb.pack(side="right", fill="y")
        self.agent_tree.configure(yscrollcommand=vsb.set)

        # Status
        self.status = tk.StringVar(value="Ready - Start by creating venvs, then start Leader and Agents")
        ttk.Label(parent, textvariable=self.status, foreground="blue").pack(anchor="w", **pad)

    def _build_plots(self, parent):
        """Build the analytics/plots tab"""
        # Create matplotlib figures
        self.fig = Figure(figsize=(14, 8), dpi=100)
        
        # 4 subplots: CPU, Memory, Energy, Workload Distribution
        self.ax_cpu = self.fig.add_subplot(2, 2, 1)
        self.ax_mem = self.fig.add_subplot(2, 2, 2)
        self.ax_energy = self.fig.add_subplot(2, 2, 3)
        self.ax_workload = self.fig.add_subplot(2, 2, 4)
        
        self.fig.tight_layout(pad=3.0)
        
        # Embed in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, parent)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        
        # Add control buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Button(btn_frame, text="🔄 Refresh Plots", command=self._update_plots).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="📸 Export Plots as PNG", command=self._export_plots).pack(side="left", padx=5)
        ttk.Label(btn_frame, text="(Plots auto-update every 3 seconds)", foreground="gray").pack(side="left", padx=10)
        
        # Initial plot
        self._update_plots()

    def _update_plots(self):
        """Update all plots with current metrics"""
        # Clear all axes
        self.ax_cpu.clear()
        self.ax_mem.clear()
        self.ax_energy.clear()
        self.ax_workload.clear()
        
        # CPU Usage Plot
        self.ax_cpu.set_title("CPU Usage Over Time", fontweight='bold')
        self.ax_cpu.set_xlabel("Time")
        self.ax_cpu.set_ylabel("CPU Usage (%)")
        self.ax_cpu.set_ylim(0, 100)
        self.ax_cpu.grid(True, alpha=0.3)
        
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
        for idx, (node_id, cpu_data) in enumerate(self.metrics.agent_cpu.items()):
            if cpu_data:
                x = list(range(len(cpu_data)))
                self.ax_cpu.plot(x, list(cpu_data), marker='o', label=node_id, 
                               color=colors[idx % len(colors)], linewidth=2)
        self.ax_cpu.legend(loc='upper left')
        
        # Memory Usage Plot
        self.ax_mem.set_title("Memory Usage Over Time", fontweight='bold')
        self.ax_mem.set_xlabel("Time")
        self.ax_mem.set_ylabel("Memory Usage (%)")
        self.ax_mem.set_ylim(0, 100)
        self.ax_mem.grid(True, alpha=0.3)
        
        for idx, (node_id, mem_data) in enumerate(self.metrics.agent_mem.items()):
            if mem_data:
                x = list(range(len(mem_data)))
                self.ax_mem.plot(x, list(mem_data), marker='s', label=node_id,
                               color=colors[idx % len(colors)], linewidth=2)
        self.ax_mem.legend(loc='upper left')
        
        # Energy Levels Plot
        self.ax_energy.set_title("Energy Levels Over Time", fontweight='bold')
        self.ax_energy.set_xlabel("Time")
        self.ax_energy.set_ylabel("Energy (%)")
        self.ax_energy.set_ylim(0, 100)
        self.ax_energy.grid(True, alpha=0.3)
        
        for idx, (node_id, energy_data) in enumerate(self.metrics.agent_energy.items()):
            if energy_data:
                x = list(range(len(energy_data)))
                self.ax_energy.plot(x, list(energy_data), marker='^', label=node_id,
                                  color=colors[idx % len(colors)], linewidth=2)
        self.ax_energy.legend(loc='upper left')
        
        # Workload Distribution (Bar Chart)
        self.ax_workload.set_title("Current Workload Distribution", fontweight='bold')
        self.ax_workload.set_xlabel("Agent Node")
        self.ax_workload.set_ylabel("Number of Containers")
        self.ax_workload.grid(True, axis='y', alpha=0.3)
        
        distribution = self.metrics.get_workload_distribution()
        if distribution:
            nodes = list(distribution.keys())
            counts = list(distribution.values())
            bars = self.ax_workload.bar(nodes, counts, color=colors[:len(nodes)], alpha=0.7)
            
            # Add value labels on bars
            for bar in bars:
                height = bar.get_height()
                self.ax_workload.text(bar.get_x() + bar.get_width()/2., height,
                                    f'{int(height)}',
                                    ha='center', va='bottom', fontweight='bold')
        
        self.canvas.draw()

    def _export_plots(self):
        """Export plots as PNG"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"edge_k8s_metrics_{timestamp}.png"
        filepath = os.path.join(BASE_DIR, filename)
        self.fig.savefig(filepath, dpi=150, bbox_inches='tight')
        self.status.set(f"Plots exported to {filename}")
        self._log_leader(f"📊 Plots exported to {filepath}")

    def _collect_metrics(self):
        """Periodically collect metrics from leader"""
        def work():
            try:
                r = requests.get(f"{LEADER_URL}/nodes", timeout=5)
                if r.ok:
                    nodes = r.json()
                    self.metrics.add_snapshot(nodes)
                    self._update_agent_status_table(nodes)
                    self._update_plots()
            except Exception:
                pass  # Leader might not be running yet
        
        threading.Thread(target=work, daemon=True).start()
        self.after(3000, self._collect_metrics)  # Collect every 3 seconds

    def _update_agent_status_table(self, nodes_data):
        """Update the agent status table with current data"""
        # Clear existing items
        for item in self.agent_tree.get_children():
            self.agent_tree.delete(item)
        
        # Add current data
        for node_id, info in nodes_data.items():
            port = info.get("addr", "").split(":")[-1] if ":" in info.get("addr", "") else "N/A"
            status = "🟢 Running"
            
            # Get metrics from the nested metrics dict
            metrics = info.get("metrics", {})
            cpu_pct = metrics.get("cpu_pct", 0)  # Already a percentage
            free_cpu = metrics.get("free_cpu", 1.0)
            free_mem_mb = metrics.get("free_mem_mb", 1564)
            energy = metrics.get("energy_pct", 100)
            mem_total_mb = metrics.get("mem_total_mb", 8000)  # Agent-specific total
            
            # Calculate usage (not free resources)
            cpu = round(cpu_pct, 1)  # Use actual CPU percentage
            
            mem_used_mb = max(0, mem_total_mb - free_mem_mb)
            mem = round((mem_used_mb / mem_total_mb) * 100, 1) if mem_total_mb > 0 else 0
            mem = max(0, min(100, mem))  # Clamp to 0-100%
            
            # Try to get container count from LEADER's tracking (not docker ps)
            # Since all agents run on same machine, docker ps shows all containers
            # Instead use leader's deployment tracking
            containers = info.get("deployments", 0)
            self.metrics.add_container_count(node_id, containers)
            
            self.agent_tree.insert("", "end", values=(
                node_id, port, status, f"{cpu}%", f"{mem}%", f"{energy}%", containers
            ))

    # --------- Button handlers ----------
    def on_make_venvs(self):
        def work():
            try:
                self.status.set("Creating/checking venvs...")
                ensure_venv(LEADER_ENV, LEADER_DIR, log=self._log_leader)
                ensure_venv(AGENT_ENV,  AGENT_DIR,  log=self._log_agent)
                self.status.set("Venvs ready. You can now start Leader and Agents.")
            except subprocess.CalledProcessError as e:
                self.status.set("Venv setup failed.")
                messagebox.showerror("venv error", str(e))
        threading.Thread(target=work, daemon=True).start()

    def on_start_leader(self):
        if not path_exists(LEADER_ENV):
            messagebox.showwarning("Leader venv", "Leader venv missing. Click 'Create/Check venvs' first.")
            return
        cmd = [LEADER_ENV, LEADER_PY]
        self.leader_proc = self.leader_proc or Proc("leader", cmd, cwd=LEADER_DIR, log=self._log_leader)
        self.leader_proc.start()
        self.status.set("Leader starting on port 8000...")

    def on_stop_leader(self):
        if self.leader_proc: self.leader_proc.stop()
        self.status.set("Leader stopped.")

    def on_start_agent(self, agent_idx):
        """Start a specific agent (0-3)"""
        if agent_idx >= len(self.agent_procs):
            # Extend list if needed
            while len(self.agent_procs) <= agent_idx:
                self.agent_procs.append(None)
        
        if self.agent_procs[agent_idx] and self.agent_procs[agent_idx].is_running():
            messagebox.showinfo("Agent", f"Agent {agent_idx+1} already running.")
            return
            
        if not path_exists(AGENT_ENV):
            messagebox.showwarning("Agent venv", "Agent venv missing. Click 'Create/Check venvs' first.")
            return

        # Ensure docker is reachable
        docker = which_docker()
        if not docker:
            messagebox.showerror("Docker not found", "docker.exe not found. Start Docker Desktop and retry.")
            return

        port = AGENT_BASE_PORT + agent_idx
        node_id = f"edge-agent-{agent_idx+1}"
        energy = 100 - (agent_idx * 10)  # Vary energy levels for demonstration
        
        env = os.environ.copy()
        env["LEADER_ADDR"] = "127.0.0.1:8000"
        env["NODE_ID"]     = node_id
        env["AGENT_PORT"]  = str(port)
        env["SIM_ENERGY"]  = str(energy)
        # (Optional) Force PATH to include docker bin
        if path_exists(DOCKER_BIN):
            env["PATH"] = DOCKER_BIN + os.pathsep + env.get("PATH","")

        cmd = [AGENT_ENV, AGENT_PY]
        proc = Proc(f"agent-{agent_idx+1}", cmd, cwd=AGENT_DIR, env=env, log=self._log_agent)
        proc.start()
        self.agent_procs[agent_idx] = proc
        self.status.set(f"Agent {agent_idx+1} starting on port {port}...")

    def on_start_all_agents(self):
        """Start all 4 agents"""
        for i in range(MAX_AGENTS):
            self.on_start_agent(i)
        self.status.set("Starting all 4 agents...")

    def on_stop_all_agents(self):
        """Stop all agents"""
        for proc in self.agent_procs:
            if proc:
                proc.stop()
        self.agent_procs = []
        self.status.set("All agents stopped.")

    def on_force_kill_all(self):
        """Nuclear option: Kill all Python processes running leader/agent"""
        def work():
            try:
                self._log_leader("[FORCE KILL] Killing all leader/agent processes...")
                
                # Stop tracked processes first
                if self.leader_proc:
                    self.leader_proc.stop()
                for proc in self.agent_procs:
                    if proc:
                        proc.stop()
                
                # On Windows, use taskkill to find and kill Flask processes
                if os.name == 'nt':
                    # Kill any python process running leader.py or agent.py
                    try:
                        result = subprocess.run(
                            ['tasklist', '/FI', 'IMAGENAME eq python.exe', '/FO', 'CSV'],
                            capture_output=True, text=True, timeout=5
                        )
                        
                        # More aggressive: kill by port
                        for port in [8000, 9000, 9001, 9002, 9003]:
                            try:
                                # Find process using the port
                                netstat_result = subprocess.run(
                                    ['netstat', '-ano', '-p', 'TCP'],
                                    capture_output=True, text=True, timeout=5
                                )
                                for line in netstat_result.stdout.split('\n'):
                                    if f':{port}' in line and 'LISTENING' in line:
                                        parts = line.split()
                                        if parts:
                                            pid = parts[-1]
                                            subprocess.run(['taskkill', '/F', '/PID', pid],
                                                         capture_output=True, timeout=3)
                                            self._log_leader(f"[FORCE KILL] Killed process on port {port} (PID: {pid})")
                            except:
                                pass
                    except Exception as e:
                        self._log_leader(f"[FORCE KILL] Error: {e}")
                
                self.leader_proc = None
                self.agent_procs = []
                self.status.set("Force kill completed. All processes should be stopped.")
                self._log_leader("[FORCE KILL] Done. You can now start fresh!")
                
            except Exception as e:
                self._log_leader(f"[FORCE KILL] Error: {e}")
                self.status.set("Force kill had errors, check logs")
        
        threading.Thread(target=work, daemon=True).start()

    def on_deploy_leader(self):
        """Deploy a single app via leader"""
        img  = self.var_image.get().strip()
        name = self.var_name.get().strip()
        # Ensure host port is free; pick next available if not
        requested_port = int(self.var_port.get())
        port = find_free_port(requested_port)

        body = {
            "image": img,
            "name": f"{name}-{int(time.time())}",  # Unique name
            "port": port,
            "resources": {"cpu": 0.05, "mem_mb": 30, "min_energy": 10}
        }
        def work():
            try:
                self.status.set("Deploying via Leader...")
                r = requests.post(f"{LEADER_URL}/deploy", json=body, timeout=30)
                self._log_leader(f"[deploy] {r.status_code} {r.text}")
                if r.ok:
                    self.metrics.total_deployments += 1
                    self.status.set(f"Deploy OK. Total deployments: {self.metrics.total_deployments}")
                else:
                    # Surface common causes
                    try:
                        err = r.json()
                    except Exception:
                        err = {"raw": r.text}
                    self.status.set("Deploy failed (Leader). See Leader Logs for error.")
                    self._log_leader(f"[deploy error] payload={body} error={err}")
            except Exception as e:
                self._log_leader(f"[deploy error] {e}")
                self.status.set("Deploy error (Leader).")
        threading.Thread(target=work, daemon=True).start()

    def on_deploy_multiple(self, count):
        """Deploy multiple apps for comparative study"""
        img  = self.var_image.get().strip()
        name = self.var_name.get().strip()
        base_port = int(self.var_port.get())
        
        def work():
            self.status.set(f"Deploying {count} apps via Leader (round-robin)...")
            success_count = 0
            
            # Deploy sequentially to ensure proper distribution
            for i in range(count):
                # Choose a free port for this app to avoid 'port already allocated'
                host_port = find_free_port(base_port + i)
                body = {
                    "image": img,
                    "name": f"{name}-{int(time.time() * 1000)}-{i}",  # More unique timestamp
                    "port": host_port,
                    "resources": {"cpu": 0.05, "mem_mb": 30, "min_energy": 10}
                }
                try:
                    r = requests.post(f"{LEADER_URL}/deploy", json=body, timeout=30)
                    if r.ok:
                        success_count += 1
                        self.metrics.total_deployments += 1
                        resp_data = r.json()
                        assigned_node = resp_data.get("node", "unknown")
                        self._log_leader(f"[deploy {i+1}/{count}] ✓ {body['name']} (port {host_port}) → {assigned_node}")
                    else:
                        # If port conflict suspected, try once more with next free port
                        retried = False
                        try:
                            errj = r.json()
                        except Exception:
                            errj = {"raw": r.text}
                        if isinstance(errj, dict) and ("port" in json.dumps(errj).lower() or "address already in use" in json.dumps(errj).lower() or "already allocated" in json.dumps(errj).lower()):
                            new_port = find_free_port(host_port + 1)
                            body_retry = dict(body)
                            body_retry["port"] = new_port
                            rr = requests.post(f"{LEADER_URL}/deploy", json=body_retry, timeout=30)
                            if rr.ok:
                                success_count += 1
                                self.metrics.total_deployments += 1
                                resp_data = rr.json()
                                assigned_node = resp_data.get("node", "unknown")
                                self._log_leader(f"[deploy {i+1}/{count}] ✓ {body_retry['name']} (retry port {new_port}) → {assigned_node}")
                                retried = True
                            else:
                                self._log_leader(f"[deploy {i+1}/{count}] ✗ Failed retry: {rr.status_code} - {rr.text}")
                        if not retried:
                            self._log_leader(f"[deploy {i+1}/{count}] ✗ Failed: {r.status_code} - {r.text}")
                    
                    # Wait between deployments to allow leader to update state
                    time.sleep(1.5)  # Increased delay for better distribution
                except Exception as e:
                    self._log_leader(f"[deploy {i+1}/{count}] ✗ Error: {e}")
            
            self.status.set(f"Deployed {success_count}/{count} apps. Total: {self.metrics.total_deployments}")
            self._log_leader(f"[deploy summary] {success_count}/{count} successful")
        
        threading.Thread(target=work, daemon=True).start()

    def on_get_nodes(self):
        def work():
            try:
                r = requests.get(f"{LEADER_URL}/nodes", timeout=10)
                self._log_leader(f"[nodes] {r.status_code} {r.text}")
                if r.ok:
                    self._update_agent_status_table(r.json())
                self.status.set("/nodes fetched and table updated.")
            except Exception as e:
                self._log_leader(f"[nodes error] {e}")
                self.status.set("/nodes error.")
        threading.Thread(target=work, daemon=True).start()

    def on_docker_ps(self):
        def work():
            try:
                out = subprocess.check_output(["docker", "ps", "--format", "table {{.Names}}\t{{.Image}}\t{{.Ports}}"], text=True)
                self._log_agent("[docker ps]\n" + out.strip())
                self.status.set("docker ps done.")
            except Exception as e:
                self._log_agent(f"[docker ps error] {e}")
                self.status.set("docker ps error.")
        threading.Thread(target=work, daemon=True).start()

    def on_cleanup(self):
        """Clean up all demo containers"""
        def work():
            try:
                # Get all running containers
                result = subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}"], 
                                      capture_output=True, text=True)
                containers = result.stdout.strip().split('\n')
                
                # Remove containers matching our naming pattern
                removed = 0
                for container in containers:
                    if container and ('demo' in container or 'miniapp' in container or 'edge' in container):
                        subprocess.call(["docker", "rm", "-f", container], 
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        removed += 1
                        self._log_agent(f"[cleanup] Removed: {container}")
                
                self._log_agent(f"[cleanup] Removed {removed} containers.")
                self.status.set(f"Cleanup done. Removed {removed} containers.")
            except Exception as e:
                self._log_agent(f"[cleanup error] {e}")
                self.status.set("Cleanup error.")
        threading.Thread(target=work, daemon=True).start()

    def on_open_app(self):
        port = int(self.var_port.get())
        open_url(f"http://127.0.0.1:{port}/")
        self.status.set(f"Opened http://127.0.0.1:{port}/")

if __name__ == "__main__":
    # Be friendly and warn if docker not found
    if not which_docker():
        print("WARNING: docker.exe not found in PATH. Start Docker Desktop and/or switch to Linux engine (docker context use desktop-linux).")
    app = App()
    app.mainloop()
