# Edge Mini-K8s

**Lightweight Kubernetes-like container orchestration system for edge computing with energy-aware scheduling, real-time analytics, and visual workload distribution across heterogeneous nodes.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-required-blue.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Screenshots](#-screenshots)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [How It Works](#-how-it-works)
- [Use Cases](#-use-cases)
- [Technologies](#-technologies)
- [Documentation](#-documentation)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)

---

## Overview

Edge Mini-K8s is a **research and educational platform** that demonstrates distributed container orchestration concepts without the complexity of full Kubernetes. Designed for edge computing environments, it simulates intelligent workload distribution across resource-constrained devices.

### What Makes It Special?

- **Lightweight**: ~1,000 lines of Python vs millions in K8s
- **Fast**: Seconds to start vs minutes for K8s clusters
- **Visual**: Real-time plots of CPU, memory, energy, and workload
- **Educational**: Perfect for learning distributed systems
- **Research-Ready**: Prototype scheduling algorithms quickly
- **Single Machine**: Runs everything locally, no VMs needed

---

## Key Features

### Intelligent Scheduling
- **Round-robin with energy awareness**: Balances load while prioritizing healthy nodes
- **Resource-aware placement**: Considers CPU, memory, and energy constraints
- **Fair distribution**: Prevents hotspots and overloading

### Real-Time Analytics
- **Live metrics collection**: Every 3 seconds from all agents
- **4 visualization plots**:
  - CPU usage over time
  - Memory usage over time
  - Energy levels
  - Workload distribution (bar chart)
- **Export capabilities**: Save plots as PNG for research papers

### Graphical Control Center
- **Tkinter GUI**: Control everything with buttons
- **4 tabs**: Controls, Analytics, Leader Logs, Agent Logs
- **One-click operations**: Start/stop components, deploy apps, cleanup
- **Status monitoring**: Real-time agent health and metrics table

### Energy-Aware Computing
- **Simulated battery levels**: Agents at 100%, 90%, 80%, 70% energy
- **Energy-conscious routing**: Higher-energy nodes preferred when loads equal
- **Research application**: Study battery-aware workload placement

### Docker Integration
- **Automatic port allocation**: Prevents port conflicts
- **Retry logic**: Handles transient failures gracefully
- **Multi-image support**: Deploy any Docker image

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    GUI (Tkinter)                        │
│  • Control buttons  • Real-time plots  • Log viewers    │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP
                      ▼
┌─────────────────────────────────────────────────────────┐
│              LEADER (Port 8000)                         │
│  • Receives deployment requests                         │
│  • Tracks available agents (heartbeats)                 │
│  • Runs scheduling algorithm                            │
│  • Routes containers to best agent                      │
└──────┬───────────┬────────────┬────────────┬───────────┘
       │           │            │            │
       ▼           ▼            ▼            ▼
    Agent-1     Agent-2      Agent-3      Agent-4
    :9000       :9001        :9002        :9003
    100%        90%          80%          70% energy
       │           │            │            │
       └───────────┴────────────┴────────────┘
                      │
                      ▼
              Docker Daemon (Local)
```

### Component Flow

1. **User** → Clicks "Deploy 10 Apps" in GUI
2. **GUI** → Sends 10 sequential POST requests to Leader
3. **Leader** → For each request:
   - Gathers online agents with metrics
   - Sorts by: fewest deployments → highest energy → most free resources
   - Picks first suitable agent
   - POSTs to Agent's `/run` endpoint
4. **Agent** → Executes `docker pull` and `docker run`
5. **Docker** → Container starts, mapped to unique host port
6. **Metrics Loop** → Every 3s, GUI polls Leader for agent status and updates plots

---

## Screenshots

### Main Control Interface
```
┌─────────────────────────────────────────────────────────┐
│ Controls & Status                                       │
├─────────────────────────────────────────────────────────┤
│ [Create/Check venvs] [Start Leader] [Stop Leader]      │
│ [Start Agent 1-4]    [Start ALL]    [FORCE KILL ALL]   │
│ [Deploy 1/5/10 Apps] [GET /nodes]   [Cleanup All]      │
├─────────────────────────────────────────────────────────┤
│ Agent Status Table:                                     │
│ ┌────────────┬──────┬─────────┬────────┬────────┬─────┐│
│ │ Node ID    │ Port │ Status  │ CPU %  │ Mem %  │ ... ││
│ │ agent-1    │ 9000 │ 🟢 Run  │ 23.5%  │ 45.2%  │ 3   ││
│ │ agent-2    │ 9001 │ 🟢 Run  │ 32.1%  │ 42.8%  │ 3   ││
│ │ agent-3    │ 9002 │ 🟢 Run  │ 18.7%  │ 48.5%  │ 2   ││
│ │ agent-4    │ 9003 │ 🟢 Run  │ 28.4%  │ 44.1%  │ 2   ││
│ └────────────┴──────┴─────────┴────────┴────────┴─────┘│
└─────────────────────────────────────────────────────────┘
```

### Real-Time Analytics
```
┌───────────────────────────────────────────────────────┐
│ 📊 Analytics & Plots                                  │
├───────────────────────────────────────────────────────┤
│  CPU Usage Over Time       │  Memory Usage Over Time  │
│  [Line graph with 4 lines] │  [Line graph with 4 lines]│
│  Different per agent       │  Varied patterns         │
├────────────────────────────┼──────────────────────────┤
│  Energy Levels             │  Workload Distribution   │
│  [Flat lines: 100%/90%...]│  [Bar chart: 3/3/2/2]   │
└───────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- **Python 3.10+** ([Download](https://www.python.org/downloads/))
- **Docker Desktop** ([Download](https://www.docker.com/products/docker-desktop/))
- **Windows 10/11** (or macOS/Linux with minor path adjustments)

### Installation

```powershell
# 1. Clone the repository
git clone https://github.com/Aditya-Ithamraju/Lightweight_container_orchestration.git
cd Lightweight_container_orchestration

# 2. Verify prerequisites
python --version    # Should be 3.10+
docker --version    # Should show Docker version

# 3. Start Docker Desktop
# (Open Docker Desktop app and wait for it to be ready)

# 4. Launch the GUI
python orchestrator_gui_advanced.py
```

### First Run

1. **Setup Environments**: Click `Create/Check venvs` (wait 1-2 minutes)
2. **Start Leader**: Click `Start Leader`
3. **Start Agents**: Click `Start ALL Agents`
4. **Deploy Apps**: Click `Deploy 5 Apps`
5. **View Metrics**: Go to `📊 Analytics & Plots` tab

**You're now orchestrating containers across 4 simulated edge nodes!**

---

## Project Structure

```
edge-mini-k8s/
├── orchestrator_gui_advanced.py    # Main GUI application
├── leader/
│   ├── leader.py                   # Leader API (Flask, ~500 lines)
│   ├── scheduler.py                # Scheduling algorithm
│   ├── requirements.txt            # Flask, requests
│   └── .venv/                      # Virtual environment (auto-created)
├── agent/
│   ├── agent.py                    # Agent API (Flask, ~200 lines)
│   ├── requirements.txt            # Flask, requests, psutil
│   └── .venv/                      # Virtual environment (auto-created)
├── scripts/
│   ├── smoke_deploy.py             # Quick deployment test script
│   └── ...
├── GETTING_STARTED.md              # Detailed setup guide
├── WORKFLOW_DIAGRAM.md             # Visual Mermaid diagrams
├── PROJECT_EXPLANATION.md          # Technical deep-dive
└── README.md                       # This file
```

### Key Files Explained

| File | Purpose | Lines of Code |
|------|---------|---------------|
| `orchestrator_gui_advanced.py` | GUI with matplotlib plots, controls | ~800 |
| `leader/leader.py` | REST API + scheduling logic | ~500 |
| `agent/agent.py` | Docker execution + metrics reporting | ~200 |
| `leader/scheduler.py` | Best-fit algorithm (legacy) | ~30 |

**Total Core Code: ~1,500 lines** (vs. millions in Kubernetes!)

---

## How It Works

### 1. Agent Registration (Heartbeat)

```python
# Every 8 seconds, each agent sends:
POST http://127.0.0.1:8000/register
{
  "node_id": "edge-agent-1",
  "addr": "127.0.0.1:9000",
  "metrics": {
    "cpu_pct": 23.5,
    "free_cpu": 0.76,
    "free_mem_mb": 5120,
    "mem_total_mb": 8000,
    "energy_pct": 100
  }
}
```

Leader stores this in `nodes[node_id]` with `last_seen` timestamp.

### 2. Scheduling Algorithm

```python
# Leader's /deploy endpoint:
1. Get all online agents (last_seen < 30s ago)
2. Sort by priority:
   - Fewest deployments (round-robin fairness)
   - Highest energy (battery-aware)
   - Most free CPU (performance)
   - Most free memory (capacity)
3. Pick first agent meeting resource constraints:
   - free_cpu >= requested_cpu
   - free_mem_mb >= requested_mem
   - energy_pct >= min_energy
4. POST to agent's /run endpoint
5. Track: deployment_counter[agent] += 1
```

**Example Distribution (10 apps):**
```
Deploy #  → Agent Selected → Reason
    1     → Agent-1        → All tied, highest energy (100%)
    2     → Agent-2        → Fewest deployments (0 < 1)
    3     → Agent-3        → Fewest deployments (0 < 1)
    4     → Agent-4        → Fewest deployments (0 < 1)
    5     → Agent-1        → All tied at 1, highest energy wins
    ...
Result: 3, 3, 2, 2 ✅ Balanced distribution!
```

### 3. Docker Execution

```python
# Agent receives POST /run:
1. docker pull {image}              # Download if not cached
2. docker run -d --rm \             # Detached, auto-remove
     --name {unique_name} \
     -p {host_port}:{container_port} \
     {image}
3. Return container_id or error
```

### 4. Metrics Simulation

Since all agents run on one machine, we simulate heterogeneous resources:

```python
# Each agent has unique characteristics:
- CPU: Base system CPU + energy-based load + per-agent offset
- Memory: Simulated total (2-8 GB range) with time-varying usage
- Energy: Static levels set at startup (100%, 90%, 80%, 70%)
```

This creates **realistic, varied plots** for research/demos.

---

## Use Cases

### 1. Education

**Teaching Distributed Systems:**
- Show how orchestration works without K8s complexity
- Demonstrate scheduling trade-offs (fairness vs. efficiency)
- Visualize workload distribution in real-time

**Course Integration:**
- Labs: "Modify scheduler to prioritize low-latency nodes"
- Projects: "Add health checks and container restart logic"
- Assignments: "Implement custom scheduling policies"

### 2. Research

**Scheduling Algorithm Studies:**
```python
# Compare strategies:
- Round-robin (current)
- Random placement
- Greedy (always pick best)
- Latency-aware
- Cost-optimized
```

**Metrics to Analyze:**
- Fairness: Standard deviation of container counts
- Efficiency: Average resource utilization
- Energy: Battery conservation metrics
- Performance: Response time, throughput

**Export Data:**
```python
# Click "📸 Export Plots as PNG" in GUI
# Or add CSV export for detailed analysis
```

### 3. Edge Computing Prototyping

**Simulate Real Scenarios:**
- Solar-powered edge devices (varying energy levels)
- Heterogeneous hardware (different CPU/RAM capacities)
- Network partitions (stop agents to simulate offline nodes)
- Burst workloads (deploy 20+ apps, observe distribution)

**Before Production:**
- Test orchestration logic locally
- Validate scheduling heuristics
- Measure overhead and resource usage
- Then port to k3s/k0s on real hardware

### 4. Demos & Presentations

**Live Demonstrations:**
- Show workload distribution visually (bar chart)
- Compare before/after of different scheduling policies
- Simulate failures (kill agents, show graceful handling)
- Real-time metrics updating every 3 seconds

---

## Technologies

### Core Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.10+ | Core language |
| **Flask** | 3.1.2 | Web framework (Leader & Agents) |
| **Docker** | 20.10+ | Container runtime |
| **Tkinter** | Built-in | GUI framework |
| **Matplotlib** | 3.10.7 | Real-time plotting |
| **psutil** | 7.1.0 | System metrics |
| **Requests** | 2.32.5 | HTTP client |

### Why These Choices?

- **Flask**: Lightweight, easy to modify, perfect for REST APIs
- **Tkinter**: Cross-platform, no extra installation needed
- **Matplotlib**: Industry-standard for scientific plots
- **psutil**: Cross-platform system metrics without admin privileges
- **In-Memory Storage**: No database overhead, fast prototyping

---

## Documentation

Comprehensive guides included in the repository:

### 1. **GETTING_STARTED.md** (Start Here!)
- Prerequisites and installation
- Detailed 5-minute quick start
- Step-by-step workflow with diagrams
- Common use cases with examples
- Troubleshooting guide (6 common problems)
- Research tips and data export

### 2. **WORKFLOW_DIAGRAM.md** (Visual Reference)
- System architecture diagram
- Agent registration/heartbeat sequence
- Deployment flow (GUI → Leader → Agent → Docker)
- Metrics collection loop
- Scheduling algorithm flowchart
- Failure modes and handling

### 3. **PROJECT_EXPLANATION.md** (Technical Deep-Dive)
- What is edge computing?
- Why metrics behave certain ways (CPU, memory)
- Technologies used (detailed)
- Local simulation vs. real deployment
- Academic research guidance
- Comparative study setup

### 4. **FIXES_APPLIED.md** (Changelog)
- Recent improvements and bug fixes
- Metrics calculation corrections
- Deployment distribution fixes
- Port conflict resolution

---

## Troubleshooting

### Common Issues

<details>
<summary><b>Problem: "Docker not found" error</b></summary>

**Solution:**
```powershell
# 1. Check Docker is running
docker ps

# 2. Verify Docker Desktop is open (look for whale icon in system tray)

# 3. Restart Docker Desktop if needed
```
</details>

<details>
<summary><b>Problem: Can't stop Leader/Agents</b></summary>

**Solution:**
```powershell
# Use the "FORCE KILL ALL" button in GUI
# Or manually:
netstat -ano | findstr :8000
taskkill /F /PID <PID>
```
</details>

<details>
<summary><b>Problem: Port already allocated</b></summary>

**Solution:**
 **Already fixed!** GUI now auto-picks free ports and retries.
</details>

<details>
<summary><b>Problem: All agents show same CPU/Memory</b></summary>

**Solution:**
 **Already fixed!** Latest version simulates varied metrics per agent.
</details>

<details>
<summary><b>Problem: Deployments fail with 404</b></summary>

**Solution:**
 **Already fixed!** `/deploy` endpoint added to `leader/leader.py`.
</details>

### Quick Diagnostics

```powershell
# Test deployment without GUI
python scripts/smoke_deploy.py nginx:alpine

# Check what's running
docker ps

# Check ports in use
netstat -ano | findstr :8000
netstat -ano | findstr :9000

# Clean slate restart
# 1. Click "FORCE KILL ALL" in GUI
# 2. Click "Cleanup All" (removes containers)
# 3. Start fresh: Start Leader → Start ALL Agents
```

---

## Contributing

Contributions are welcome! Here are some ideas:

### Easy Contributions
- Add more Docker test images to `scripts/`
- Improve error messages in GUI
- Add tooltips to buttons
- Create video tutorial

### Moderate Contributions
- Implement health checks (ping containers periodically)
- Add container restart logic on failure
- Export metrics to CSV for analysis
- Add more scheduling algorithms (latency-aware, cost-based)

### Advanced Contributions
- Multi-machine support (run agents on different computers)
- Persistent state (save/load cluster state)
- Web-based GUI (Flask + React)
- Integration with k3s/k0s

### How to Contribute

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## Comparison: Mini-K8s vs. Full Kubernetes

| Aspect | Edge Mini-K8s | Kubernetes |
|--------|---------------|------------|
| **Lines of Code** | ~1,500 | Millions |
| **RAM Required** | ~250 MB | 4+ GB |
| **Startup Time** | 5 seconds | Minutes |
| **Components** | 3 (GUI, Leader, Agent) | 10+ services |
| **Setup Steps** | 1 command | Multi-step cluster init |
| **Config Files** | 0 (env vars only) | Dozens of YAML files |
| **Learning Curve** | Hours | Weeks/Months |
| **Ideal For** | Learning, Research, Prototyping | Production Deployments |
| **Scheduling** | Custom algorithms (easy to modify) | Complex priority functions |
| **Visualization** | Built-in GUI with plots | External tools (Grafana) |

---

## Acknowledgments

- Inspired by Kubernetes' orchestration model
- Built for edge computing research and education
- Designed to be hackable and educational

---

## Contact

**Aditya Ithamraju**
- GitHub: [@Aditya-Ithamraju](https://github.com/Aditya-Ithamraju)
- Repository: [Lightweight Container Orchestration](https://github.com/Aditya-Ithamraju/Lightweight_container_orchestration)

---

## 🚀 What's Next?

### Roadmap

- [ ] Web-based GUI (Flask + React)
- [ ] Multi-machine deployment support
- [ ] Container health checks and auto-restart
- [ ] Persistent state (save/load cluster configuration)
- [ ] Prometheus metrics export
- [ ] Integration examples with k3s/k0s
- [ ] Video tutorials and demos
- [ ] Jupyter notebooks for research analysis

### Related Projects

- **k3s**: Lightweight Kubernetes for production
- **k0s**: Zero-friction Kubernetes
- **MicroK8s**: Canonical's lightweight K8s
- **KubeEdge**: Kubernetes-native edge computing platform

---

<div align="center">

[⬆ Back to Top](#-edge-mini-k8s)

</div>
