import os, subprocess, requests, threading, tkinter as tk
from tkinter import messagebox, ttk, simpledialog
import customtkinter as ctk

# ---------- THEME ----------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")  # options: "blue", "dark-blue", "green"

# ---------- GLOBALS ----------
leader_proc = None
agents = []
next_port = 9000

# ---------- UTILS ----------
def log(msg):
    logbox.insert(tk.END, msg + "\n")
    logbox.see(tk.END)

# ---------- LEADER CONTROL ----------
def start_leader():
    global leader_proc
    if leader_proc:
        messagebox.showinfo("Leader", "Leader already running.")
        return
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    leader_proc = subprocess.Popen(
        ["python", "leader/leader.py"],
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    log("🚀 Leader started on port 8000")

def stop_leader():
    global leader_proc
    if leader_proc:
        leader_proc.terminate()
        leader_proc = None
        log("🛑 Leader stopped")

# ---------- AGENT CONTROL ----------
def add_agent():
    global next_port
    port = next_port
    next_port += 1
    node_id = f"edge-{len(agents)+1}"

    env = os.environ.copy()
    env["LEADER_ADDR"] = "127.0.0.1:8000"
    env["NODE_ID"] = node_id
    env["AGENT_PORT"] = str(port)
    env["SIM_ENERGY"] = "80"
    env["PYTHONUNBUFFERED"] = "1"

    p = subprocess.Popen(["python", "agent/agent.py"], env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)
    agents.append({"id": node_id, "port": port, "proc": p})
    refresh_table()
    log(f"🧩 Started {node_id} @ port {port}")

def stop_agent(agent_id):
    for a in agents:
        if a["id"] == agent_id:
            a["proc"].terminate()
            agents.remove(a)
            log(f"❌ Stopped {agent_id}")
            break
    refresh_table()

def stop_all_agents():
    for a in agents:
        try:
            a["proc"].terminate()
        except Exception:
            pass
    agents.clear()
    refresh_table()
    log("⛔ All agents stopped")

# ---------- LEADER REQUESTS ----------
def deploy_one():
    image, name, port = img_var.get(), name_var.get(), port_var.get()
    body = {"image": image, "name": name, "port": int(port),
            "resources":{"cpu":0.05,"mem_mb":30,"min_energy":10}}
    try:
        r = requests.post("http://127.0.0.1:8000/deploy", json=body, timeout=5)
        log(f"Deploy→ {r.status_code} {r.text}")
    except Exception as e:
        log(f"⚠️ Deploy failed: {e}")

def deploy_all():
    for a in agents:
        try:
            requests.post(f"http://127.0.0.1:{a['port']}/run", json={
                "image": img_var.get(),
                "name": name_var.get(),
                "port": int(port_var.get())
            }, timeout=5)
            log(f"✅ Deployed on {a['id']}")
        except Exception as e:
            log(f"⚠️ {a['id']} deploy error: {e}")

def get_nodes():
    try:
        r = requests.get("http://127.0.0.1:8000/nodes", timeout=5)
        nodes = r.json()
        update_status_table(nodes)
        log("🧠 Node metrics updated")
    except Exception as e:
        log(f"Error getting nodes: {e}")

# ---------- TABLE UPDATES ----------
def refresh_table():
    for i in tbl.get_children():
        tbl.delete(i)
    for a in agents:
        tbl.insert("", "end", values=(a["id"], f"127.0.0.1:{a['port']}", "Running", "-", "-"))

def update_status_table(nodes):
    for i in tbl.get_children():
        tbl.delete(i)
    for nid, info in nodes.items():
        cpu = round((1 - info["free_cpu"]) * 100, 1)
        mem = round((1564 - info["free_mem_mb"]) / 1564 * 100, 1)
        tbl.insert("", "end",
                   values=(nid, info["addr"], f"{cpu}%", f"{mem}%", info["energy_pct"]))

# ---------- CONTAINER MANAGEMENT ----------
def list_containers():
    """Show containers running on Agent 1 in a popup table."""
    try:
        resp = requests.get("http://127.0.0.1:9000/containers", timeout=5)
        containers = resp.json()
    except Exception as e:
        log(f"List failed: {e}")
        return

    popup = ctk.CTkToplevel(root)
    popup.title("Running Containers")
    popup.geometry("700x400")
    popup.grab_set()

    ctk.CTkLabel(popup, text="🧾 Running Containers on Agent 9000",
                 font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)

    frame = ctk.CTkFrame(popup)
    frame.pack(fill="both", expand=True, padx=15, pady=10)

    cols = ("Name", "Image", "Ports")
    tree = ttk.Treeview(frame, columns=cols, show="headings", height=10)
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=200, anchor="center")
    tree.pack(fill="both", expand=True, padx=10, pady=10)

    for c in containers:
        tree.insert("", "end", values=(c.get("name", ""), c.get("image", ""), c.get("ports", "")))

    ctk.CTkButton(popup, text="Close", command=popup.destroy).pack(pady=10)

def stop_container():
    """Stop a running container by name."""
    name = simpledialog.askstring("Stop Container", "Enter container name:")
    if not name:
        return
    try:
        resp = requests.post("http://127.0.0.1:9000/stop", json={"name": name}, timeout=5)
        messagebox.showinfo("Result", f"Stopped: {name}")
        log(resp.text)
    except Exception as e:
        log(f"Stop failed: {e}")

# ---------- AUTO REFRESH ----------
def auto_refresh():
    get_nodes()
    root.after(5000, auto_refresh)

# ---------- UI LAYOUT ----------
root = ctk.CTk()
root.title("Mini-Orchestrator Dashboard")
root.geometry("1100x720")
root.configure(fg_color="#0f1115")

main_frame = ctk.CTkFrame(root, corner_radius=25, fg_color="#1a1d23")
main_frame.pack(padx=20, pady=20, fill="both", expand=True)

header = ctk.CTkLabel(main_frame, text="🪩 Edge Mini-K8s Control Center",
                      font=ctk.CTkFont(size=26, weight="bold"))
header.pack(pady=(10, 15))

# Input area
env_frame = ctk.CTkFrame(main_frame, corner_radius=15)
env_frame.pack(fill="x", padx=15, pady=5)
img_var = tk.StringVar(value="krishna2530/mini-test-app:latest")
name_var = tk.StringVar(value="demo-app")
port_var = tk.StringVar(value="5050")

for label, var, width in [("Image", img_var, 300), ("Name", name_var, 150), ("Port", port_var, 70)]:
    ctk.CTkLabel(env_frame, text=label).pack(side="left", padx=6)
    ctk.CTkEntry(env_frame, textvariable=var, width=width).pack(side="left", padx=6)

# Buttons
btn_frame = ctk.CTkFrame(main_frame, corner_radius=15)
btn_frame.pack(fill="x", padx=15, pady=5)
for txt, cmd in [
    ("Start Leader", start_leader),
    ("Stop Leader", stop_leader),
    ("➕ Add Agent", add_agent),
    ("⛔ Stop All Agents", stop_all_agents),
    ("Deploy via Leader", deploy_one),
    ("Deploy to All", deploy_all),
    ("🧾 List Containers", list_containers),
    ("🛑 Stop Container", stop_container),
    ("Refresh Nodes", get_nodes)
]:
    ctk.CTkButton(btn_frame, text=txt, command=cmd, width=130, height=32,
                  corner_radius=12, fg_color="#0078D7",
                  hover_color="#0099ff").pack(side="left", padx=6, pady=6)

# Agents table
tbl_frame = ctk.CTkFrame(main_frame, corner_radius=15)
tbl_frame.pack(fill="both", expand=True, padx=15, pady=5)
cols = ("Node ID", "Address", "CPU Usage", "Mem Usage", "Energy %")
tbl = ttk.Treeview(tbl_frame, columns=cols, show="headings", height=8)
for c in cols:
    tbl.heading(c, text=c)
    tbl.column(c, width=180, anchor="center")
tbl.pack(fill="both", expand=True, padx=10, pady=5)

# Log area
log_frame = ctk.CTkFrame(main_frame, corner_radius=15)
log_frame.pack(fill="both", expand=True, padx=15, pady=5)
ctk.CTkLabel(log_frame, text="Logs / Events", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=10)
logbox = tk.Text(log_frame, height=8, bg="#111", fg="#0f0",
                 font=("Consolas", 10), relief="flat", wrap="word")
logbox.pack(fill="both", expand=True, padx=10, pady=5)
log("✨ Ready")

# Auto refresh loop
root.after(5000, auto_refresh)
root.mainloop()
