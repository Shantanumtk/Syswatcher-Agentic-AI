import os
import psutil
import paramiko
import socket
from langchain_core.tools import tool

def _get_server_ssh(server_name: str):
    """Get SSH details from syswatcher.conf."""
    conf_path = "/app/syswatcher.conf"
    if os.path.exists(conf_path):
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    if key.strip() == server_name:
                        parts = val.strip().split()
                        if len(parts) >= 3:
                            return parts[0], parts[1], parts[2]
    # fallback to DB
    try:
        import psycopg2
        db_url = os.getenv("DATABASE_URL", "")
        if db_url:
            conn = psycopg2.connect(db_url)
            cur = conn.cursor()
            cur.execute("SELECT ip, ssh_user, ssh_key_path FROM servers WHERE name=%s AND active=true", (server_name,))
            row = cur.fetchone()
            conn.close()
            if row:
                return row[0], row[1], row[2]
    except Exception:
        pass
    return None, None, None

def _ssh_run(server_name: str, cmd: str, timeout: int = 10) -> str:
    """Run command on remote server via SSH."""
    ip, user, key_path = _get_server_ssh(server_name)
    if not ip:
        return f"ERROR: Server {server_name} not found"
    if not key_path or not os.path.exists(key_path):
        return f"ERROR: SSH key not found: {key_path}"
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=user, key_filename=key_path, timeout=8, banner_timeout=8)
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        client.close()
        return out if out else err
    except Exception as e:
        return f"ERROR: {e}"

def _is_remote(server_name: str) -> bool:
    return server_name not in ("local", "localhost", "", None)

@tool
def get_cpu_stats(server_name: str = "local") -> dict:
    """Get CPU usage percentage and per-core breakdown.
    Use when asked: what is CPU usage, is CPU high, CPU stats
    server_name: which server to check (default: local)
    """
    if not _is_remote(server_name):
        per_core = psutil.cpu_percent(percpu=True, interval=1)
        la = psutil.getloadavg()
        return {
            "server": server_name,
            "cpu_percent": psutil.cpu_percent(interval=1),
            "per_core": per_core,
            "core_count": psutil.cpu_count(),
            "load_avg_1m": la[0],
            "load_avg_5m": la[1],
            "load_avg_15m": la[2],
        }
    # Remote via SSH
    out = _ssh_run(server_name, "top -bn1 | grep Cpu && nproc && cat /proc/loadavg")
    if out.startswith("ERROR"):
        return {"error": out, "server": server_name}
    try:
        lines = out.strip().splitlines()
        cpu_line = next((l for l in lines if "Cpu" in l or "cpu" in l), "")
        idle = 0.0
        for part in cpu_line.split(","):
            if "id" in part:
                idle = float(part.strip().split()[0].replace("%id","").replace("ni","").strip())
                break
        cpu_pct = round(100.0 - idle, 1)
        core_count = int(lines[-2]) if len(lines) >= 2 else 1
        load_parts = lines[-1].split() if lines else ["0","0","0"]
        return {
            "server": server_name,
            "cpu_percent": cpu_pct,
            "per_core": [cpu_pct],
            "core_count": core_count,
            "load_avg_1m": float(load_parts[0]) if load_parts else 0,
            "load_avg_5m": float(load_parts[1]) if len(load_parts) > 1 else 0,
            "load_avg_15m": float(load_parts[2]) if len(load_parts) > 2 else 0,
        }
    except Exception as e:
        return {"error": str(e), "raw": out, "server": server_name}

@tool
def get_memory_stats(server_name: str = "local") -> dict:
    """Get RAM and swap usage.
    Use when asked: memory usage, RAM stats, is memory high, swap usage
    server_name: which server to check (default: local)
    """
    if not _is_remote(server_name):
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        return {
            "server": server_name,
            "total_gb": round(vm.total / 1e9, 2),
            "used_gb": round(vm.used / 1e9, 2),
            "available_gb": round(vm.available / 1e9, 2),
            "percent": vm.percent,
            "swap_total_gb": round(sw.total / 1e9, 2),
            "swap_used_gb": round(sw.used / 1e9, 2),
            "swap_percent": sw.percent,
        }
    out = _ssh_run(server_name, "free -b")
    if out.startswith("ERROR"):
        return {"error": out, "server": server_name}
    try:
        lines = out.splitlines()
        mem = lines[1].split()
        swap = lines[2].split() if len(lines) > 2 else ["Swap","0","0","0"]
        total = int(mem[1]); used = int(mem[2]); avail = int(mem[6]) if len(mem) > 6 else int(mem[3])
        s_total = int(swap[1]); s_used = int(swap[2])
        return {
            "server": server_name,
            "total_gb": round(total / 1e9, 2),
            "used_gb": round(used / 1e9, 2),
            "available_gb": round(avail / 1e9, 2),
            "percent": round(used / total * 100, 1) if total > 0 else 0,
            "swap_total_gb": round(s_total / 1e9, 2),
            "swap_used_gb": round(s_used / 1e9, 2),
            "swap_percent": round(s_used / s_total * 100, 1) if s_total > 0 else 0,
        }
    except Exception as e:
        return {"error": str(e), "raw": out, "server": server_name}

@tool
def get_disk_usage(server_name: str = "local", path: str = "/") -> dict:
    """Get disk usage for a mount point.
    Use when asked: disk usage, disk space, is disk full
    server_name: which server to check (default: local)
    path: mount point (default: /)
    """
    if not _is_remote(server_name):
        try:
            usage = psutil.disk_usage(path)
            io = psutil.disk_io_counters()
            return {
                "server": server_name,
                "path": path,
                "total_gb": round(usage.total / 1e9, 2),
                "used_gb": round(usage.used / 1e9, 2),
                "free_gb": round(usage.free / 1e9, 2),
                "percent": usage.percent,
                "read_mb": round(io.read_bytes / 1e6, 2) if io else None,
                "write_mb": round(io.write_bytes / 1e6, 2) if io else None,
            }
        except FileNotFoundError:
            return {"error": f"Mount point {path} not found"}
    out = _ssh_run(server_name, f"df -B1 {path}")
    if out.startswith("ERROR"):
        return {"error": out, "server": server_name}
    try:
        lines = out.splitlines()
        parts = lines[1].split()
        total = int(parts[1]); used = int(parts[2]); free = int(parts[3])
        pct = round(used / total * 100, 1) if total > 0 else 0
        return {
            "server": server_name,
            "path": path,
            "total_gb": round(total / 1e9, 2),
            "used_gb": round(used / 1e9, 2),
            "free_gb": round(free / 1e9, 2),
            "percent": pct,
        }
    except Exception as e:
        return {"error": str(e), "raw": out, "server": server_name}

@tool
def get_network_stats(server_name: str = "local") -> dict:
    """Get network interface stats — bytes sent/received, packets, errors.
    Use when asked: network stats, bandwidth usage, network errors
    server_name: which server to check (default: local)
    """
    if not _is_remote(server_name):
        net = psutil.net_io_counters(pernic=True)
        result = {}
        for iface, stats in net.items():
            if iface == "lo":
                continue
            result[iface] = {
                "bytes_sent_mb": round(stats.bytes_sent / 1e6, 2),
                "bytes_recv_mb": round(stats.bytes_recv / 1e6, 2),
                "packets_sent": stats.packets_sent,
                "packets_recv": stats.packets_recv,
                "errors_in": stats.errin,
                "errors_out": stats.errout,
                "drop_in": stats.dropin,
                "drop_out": stats.dropout,
            }
        return {"server": server_name, "interfaces": result}
    out = _ssh_run(server_name, "cat /proc/net/dev")
    if out.startswith("ERROR"):
        return {"error": out, "server": server_name}
    try:
        result = {}
        for line in out.splitlines()[2:]:
            parts = line.split()
            if not parts:
                continue
            iface = parts[0].rstrip(":")
            if iface == "lo":
                continue
            result[iface] = {
                "bytes_recv_mb": round(int(parts[1]) / 1e6, 2),
                "packets_recv": int(parts[2]),
                "bytes_sent_mb": round(int(parts[9]) / 1e6, 2),
                "packets_sent": int(parts[10]),
                "errors_in": int(parts[3]),
                "errors_out": int(parts[11]),
            }
        return {"server": server_name, "interfaces": result}
    except Exception as e:
        return {"error": str(e), "raw": out, "server": server_name}

@tool
def get_top_processes(server_name: str = "local", limit: int = 10) -> list:
    """Get top N processes by CPU usage.
    Use when asked: top processes, what is using CPU, busy processes
    server_name: which server to check (default: local)
    """
    if not _is_remote(server_name):
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return sorted(procs, key=lambda x: x.get("cpu_percent") or 0, reverse=True)[:limit]
    out = _ssh_run(server_name, f"ps aux --sort=-%cpu | head -{limit+1}")
    if out.startswith("ERROR"):
        return [{"error": out}]
    try:
        procs = []
        for line in out.splitlines()[1:]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                procs.append({
                    "pid": int(parts[1]),
                    "name": parts[10][:30],
                    "cpu_percent": float(parts[2]),
                    "memory_percent": float(parts[3]),
                    "status": parts[7],
                })
        return procs
    except Exception as e:
        return [{"error": str(e), "raw": out}]

@tool
def get_system_uptime(server_name: str = "local") -> dict:
    """Get system uptime and boot time.
    Use when asked: uptime, how long has server been running, last reboot
    server_name: which server to check (default: local)
    """
    if not _is_remote(server_name):
        import datetime
        boot = psutil.boot_time()
        uptime_s = psutil.time.time() - boot
        days = int(uptime_s // 86400)
        hours = int((uptime_s % 86400) // 3600)
        minutes = int((uptime_s % 3600) // 60)
        return {
            "server": server_name,
            "boot_time": datetime.datetime.fromtimestamp(boot).isoformat(),
            "uptime_days": days, "uptime_hours": hours, "uptime_mins": minutes,
            "uptime_str": f"{days}d {hours}h {minutes}m",
        }
    out = _ssh_run(server_name, "uptime -s && uptime -p")
    if out.startswith("ERROR"):
        return {"error": out, "server": server_name}
    lines = out.splitlines()
    return {
        "server": server_name,
        "boot_time": lines[0] if lines else "unknown",
        "uptime_str": lines[1] if len(lines) > 1 else "unknown",
    }

@tool
def get_load_average(server_name: str = "local") -> dict:
    """Get system load average for 1, 5, and 15 minutes.
    Use when asked: load average, system load, is load high
    server_name: which server to check (default: local)
    """
    if not _is_remote(server_name):
        la = psutil.getloadavg()
        cores = psutil.cpu_count()
        return {
            "server": server_name,
            "load_1m": la[0], "load_5m": la[1], "load_15m": la[2],
            "cpu_cores": cores,
            "load_per_core_1m": round(la[0] / cores, 2) if cores else None,
            "status": "high" if la[0] > cores else "normal",
        }
    out = _ssh_run(server_name, "cat /proc/loadavg && nproc")
    if out.startswith("ERROR"):
        return {"error": out, "server": server_name}
    try:
        lines = out.splitlines()
        parts = lines[0].split()
        cores = int(lines[1]) if len(lines) > 1 else 1
        la1, la5, la15 = float(parts[0]), float(parts[1]), float(parts[2])
        return {
            "server": server_name,
            "load_1m": la1, "load_5m": la5, "load_15m": la15,
            "cpu_cores": cores,
            "load_per_core_1m": round(la1 / cores, 2),
            "status": "high" if la1 > cores else "normal",
        }
    except Exception as e:
        return {"error": str(e), "raw": out, "server": server_name}

@tool
def get_open_ports(server_name: str = "local") -> list:
    """Get list of open listening ports and which process owns them.
    Use when asked: open ports, listening services, what ports are open
    server_name: which server to check (default: local)
    """
    if not _is_remote(server_name):
        result = []
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == "LISTEN":
                try:
                    proc = psutil.Process(conn.pid).name() if conn.pid else "unknown"
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    proc = "unknown"
                result.append({
                    "port": conn.laddr.port,
                    "address": conn.laddr.ip,
                    "pid": conn.pid,
                    "process": proc,
                })
        return sorted(result, key=lambda x: x["port"])
    out = _ssh_run(server_name, "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null")
    if out.startswith("ERROR"):
        return [{"error": out}]
    try:
        result = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if not parts:
                continue
            addr = parts[3] if len(parts) > 3 else parts[-1]
            if ":" in addr:
                port = addr.split(":")[-1]
                try:
                    result.append({"port": int(port), "address": addr, "server": server_name})
                except ValueError:
                    pass
        return sorted(result, key=lambda x: x.get("port", 0))
    except Exception as e:
        return [{"error": str(e), "raw": out}]
