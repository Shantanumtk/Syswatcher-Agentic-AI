import psutil
from langchain_core.tools import tool

@tool
def get_process_by_name(name: str) -> list:
    """Find running processes by name.
    Use when asked: 'is nginx running?', 'find process X', 'is mysql up?'
    name: partial process name to search e.g. 'nginx', 'python', 'java'
    """
    matches = []
    for p in psutil.process_iter(["pid", "name", "status", "cpu_percent", "memory_percent", "create_time"]):
        try:
            if name.lower() in p.info["name"].lower():
                matches.append({
                    "pid":        p.info["pid"],
                    "name":       p.info["name"],
                    "status":     p.info["status"],
                    "cpu_pct":    p.info["cpu_percent"],
                    "mem_pct":    round(p.info["memory_percent"], 2),
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return matches if matches else [{"info": f"No process matching '{name}' found"}]

@tool
def get_zombie_processes() -> list:
    """Find zombie (defunct) processes on the system.
    Use when asked: 'zombie processes', 'defunct processes', 'are there zombies?'
    """
    zombies = []
    for p in psutil.process_iter(["pid", "name", "status", "ppid"]):
        try:
            if p.info["status"] == psutil.STATUS_ZOMBIE:
                zombies.append({
                    "pid":    p.info["pid"],
                    "name":   p.info["name"],
                    "ppid":   p.info["ppid"],
                    "status": p.info["status"],
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return zombies if zombies else [{"info": "No zombie processes found"}]
