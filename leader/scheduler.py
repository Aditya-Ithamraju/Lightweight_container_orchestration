# leader/scheduler.py
import time

def choose_node(nodes, req):
    """
    nodes: dict node_id -> info
    req: dict: {"cpu": fraction (0-1), "mem_mb": int, "min_energy": int}
    returns node_id or None
    """
    required_cpu = req.get("cpu", 0.0)
    required_mem = req.get("mem_mb", 0)
    min_energy = req.get("min_energy", 10)

    # sort nodes by free_cpu desc then free_mem desc (simple best-fit)
    sorted_nodes = sorted(nodes.items(), key=lambda kv: (
        -(kv[1].get("free_cpu", 1.0)), -(kv[1].get("free_mem_mb", 1024))
    ))

    for nid, info in sorted_nodes:
        free_cpu = info.get("free_cpu", 1.0)
        free_mem = info.get("free_mem_mb", 1024)
        energy = info.get("energy_pct", 100)
        # All metrics expected: free_cpu in (0-1), free_mem_mb int, energy_pct 0-100
        if free_cpu >= required_cpu and free_mem >= required_mem and energy >= min_energy:
            return nid
    return None
