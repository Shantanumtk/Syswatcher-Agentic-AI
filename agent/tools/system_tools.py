import psutil
import socket
from langchain_core.tools import tool

@tool
def get_cpu_stats() -> dict:
    """Get current CPU usage percentage and per-core breakdown.
    Use when asked: 'what is CPU usage?', 'is CPU high?', 'CPU stats'
    """
    per_core = psutil.cpu_percent(percpu=True, interval=1)
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "per_core": per_core,
        "core_count": psutil.cpu_count(),
        "load_avg_1m": psutil.getloadavg()[0],
        "load_avg_5m": psutil.getloadavg()[1],
        "load_avg_15m": psutil.getloadavg()[2],
    }

@tool
def get_memory_stats() -> dict:
    """Get RAM and swap usage.
    Use when asked: 'memory usage', 'RAM stats', 'is memory high?', 'swap usage'
    """
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return {
        "total_gb":     round(vm.total / 1e9, 2),
        "used_gb":      round(vm.used / 1e9, 2),
        "available_gb": round(vm.available / 1e9, 2),
        "percent":      vm.percent,
        "swap_total_gb": round(sw.total / 1e9, 2),
        "swap_used_gb":  round(sw.used / 1e9, 2),
        "swap_percent":  sw.percent,
    }

@tool
def get_disk_usage(path: str = "/") -> dict:
    """Get disk usage for a specific mount point.
    Use when asked: 'disk usage', 'disk space on /var', 'is disk full?'
    Default path is /. Pass specific mount like /var, /home, /data.
    """
    try:
        usage = psutil.disk_usage(path)
        io = psutil.disk_io_counters()
        return {
            "path":       path,
            "total_gb":   round(usage.total / 1e9, 2),
            "used_gb":    round(usage.used / 1e9, 2),
            "free_gb":    round(usage.free / 1e9, 2),
            "percent":    usage.percent,
            "read_mb":    round(io.read_bytes / 1e6, 2) if io else None,
            "write_mb":   round(io.write_bytes / 1e6, 2) if io else None,
        }
    except FileNotFoundError:
        return {"error": f"Mount point {path} not found"}

@tool
def get_network_stats() -> dict:
    """Get network interface stats — bytes sent/received, packets, errors.
    Use when asked: 'network stats', 'bandwidth usage', 'network errors'
    """
    net = psutil.net_io_counters(pernic=True)
    result = {}
    for iface, stats in net.items():
        if iface == "lo":
            continue
        result[iface] = {
            "bytes_sent_mb":   round(stats.bytes_sent / 1e6, 2),
            "bytes_recv_mb":   round(stats.bytes_recv / 1e6, 2),
            "packets_sent":    stats.packets_sent,
            "packets_recv":    stats.packets_recv,
            "errors_in":       stats.errin,
            "errors_out":      stats.errout,
            "drop_in":         stats.dropin,
            "drop_out":        stats.dropout,
        }
    return result

@tool
def get_top_processes(limit: int = 10) -> list:
    """Get top N processes by CPU usage.
    Use when asked: 'top processes', 'what is using CPU?', 'busy processes'
    """
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return sorted(procs, key=lambda x: x.get("cpu_percent") or 0, reverse=True)[:limit]

@tool
def get_system_uptime() -> dict:
    """Get system uptime and boot time.
    Use when asked: 'uptime', 'how long has server been running?', 'last reboot'
    """
    import datetime
    boot = psutil.boot_time()
    uptime_s = psutil.time.time() - boot
    days    = int(uptime_s // 86400)
    hours   = int((uptime_s % 86400) // 3600)
    minutes = int((uptime_s % 3600) // 60)
    return {
        "boot_time":    datetime.datetime.fromtimestamp(boot).isoformat(),
        "uptime_days":  days,
        "uptime_hours": hours,
        "uptime_mins":  minutes,
        "uptime_str":   f"{days}d {hours}h {minutes}m",
    }

@tool
def get_load_average() -> dict:
    """Get system load average for 1, 5, and 15 minutes.
    Use when asked: 'load average', 'system load', 'is load high?'
    """
    la = psutil.getloadavg()
    cores = psutil.cpu_count()
    return {
        "load_1m":   la[0],
        "load_5m":   la[1],
        "load_15m":  la[2],
        "cpu_cores": cores,
        "load_per_core_1m": round(la[0] / cores, 2) if cores else None,
        "status": "high" if la[0] > cores else "normal",
    }

@tool
def get_open_ports() -> list:
    """Get list of open listening ports and which process owns them.
    Use when asked: 'open ports', 'listening services', 'what ports are open?'
    """
    result = []
    for conn in psutil.net_connections(kind="inet"):
        if conn.status == "LISTEN":
            try:
                proc = psutil.Process(conn.pid).name() if conn.pid else "unknown"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                proc = "unknown"
            result.append({
                "port":    conn.laddr.port,
                "address": conn.laddr.ip,
                "pid":     conn.pid,
                "process": proc,
            })
    return sorted(result, key=lambda x: x["port"])
