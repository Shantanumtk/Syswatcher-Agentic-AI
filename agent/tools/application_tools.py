import os
import subprocess
import paramiko
import requests
import socket
from langchain_core.tools import tool

def _get_server_ssh(server_name: str):
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
    return None, None, None

def _run(server_name: str, cmd: str, timeout: int = 10) -> str:
    if server_name in ("local", "localhost", ""):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return r.stdout + r.stderr
        except Exception as e:
            return str(e)
    ip, user, key_path = _get_server_ssh(server_name)
    if not ip:
        return f"Server {server_name} not found"
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=user, key_filename=key_path, timeout=8, banner_timeout=8)
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode() + stderr.read().decode()
        client.close()
        return out
    except Exception as e:
        return f"SSH error: {e}"

@tool
def check_port_open(server_name: str = "local", port: int = 80, host: str = "localhost") -> dict:
    """Check if a specific port is open and responding.
    Use when asked: is port X open, check port 3000, is service on port X, port connectivity
    server_name: local, dev, or test
    port: port number to check
    host: host to check (default: localhost)
    """
    out = _run(server_name, f"nc -zv -w3 {host} {port} 2>&1 || (echo | timeout 3 bash -c 'cat < /dev/null > /dev/tcp/{host}/{port}' 2>&1 && echo 'open' || echo 'closed')")
    is_open = "open" in out.lower() or "succeeded" in out.lower() or "connected" in out.lower()
    return {"server": server_name, "host": host, "port": port, "open": is_open, "response": out.strip()[:200]}

@tool
def check_url_health(url: str, expected_status: int = 200, timeout: int = 10) -> dict:
    """Check if a URL is healthy and returning expected status code.
    Use when asked: is website up, check URL health, HTTP health check, is endpoint responding
    url: full URL to check e.g. http://localhost:8000/health
    expected_status: expected HTTP status code (default 200)
    timeout: timeout in seconds (default 10)
    """
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        return {
            "url": url,
            "status_code": r.status_code,
            "healthy": r.status_code == expected_status,
            "response_time_ms": round(r.elapsed.total_seconds() * 1000, 2),
            "content_length": len(r.content),
            "headers": dict(list(r.headers.items())[:5]),
        }
    except requests.exceptions.ConnectionError:
        return {"url": url, "healthy": False, "error": "Connection refused — service may be down"}
    except requests.exceptions.Timeout:
        return {"url": url, "healthy": False, "error": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"url": url, "healthy": False, "error": str(e)}

@tool
def check_process_alive(server_name: str = "local", process_name: str = "nginx") -> dict:
    """Check if a named process is running.
    Use when asked: is nginx running, is postgres alive, check if process X is up
    server_name: local, dev, or test
    process_name: process name to check e.g. nginx, postgres, redis-server, docker
    """
    out = _run(server_name, f"pgrep -a {process_name} 2>/dev/null | head -5 || ps aux | grep -v grep | grep {process_name} | head -5")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    is_running = bool(lines) and "SSH error" not in out
    return {
        "server": server_name,
        "process": process_name,
        "running": is_running,
        "instances": len(lines),
        "details": lines[:5],
    }

@tool
def get_docker_containers(server_name: str = "local") -> list:
    """List all Docker containers and their status.
    Use when asked: list containers, docker containers, what containers are running, docker status
    server_name: local, dev, or test
    """
    out = _run(server_name, "docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}' 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if "command not found" in out.lower() or "Cannot connect" in out:
        return [{"error": "Docker not available on this server"}]
    return lines if lines else [{"info": "No Docker containers found"}]

@tool
def get_docker_stats(server_name: str = "local") -> list:
    """Get Docker container resource usage (CPU, memory).
    Use when asked: docker CPU usage, container memory, docker resource usage, container stats
    server_name: local, dev, or test
    """
    out = _run(server_name, "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}' 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if "command not found" in out.lower():
        return [{"error": "Docker not available"}]
    return lines if lines else [{"info": "No running containers"}]

@tool
def get_service_logs(server_name: str = "local", service: str = "nginx", lines: int = 50) -> list:
    """Get recent logs from a systemd service using journalctl.
    Use when asked: nginx logs, show service logs, journalctl for X, service log output
    server_name: local, dev, or test
    service: service name e.g. nginx, apache2, postgresql, docker
    lines: number of log lines (default 50)
    """
    out = _run(server_name, f"journalctl -u {service} --no-pager -n {lines} 2>/dev/null || systemctl status {service} 2>/dev/null | tail -{lines}")
    result = [l.strip() for l in out.splitlines() if l.strip()]
    return result if result else [f"No logs found for service: {service}"]

@tool
def get_environment_check(server_name: str = "local") -> dict:
    """Check critical environment variables and system configuration.
    Use when asked: environment check, system config, verify env vars, configuration audit
    server_name: local, dev, or test
    """
    out = _run(server_name, "ulimit -a 2>/dev/null | head -15 && echo '---' && cat /proc/sys/vm/swappiness 2>/dev/null && echo '---' && sysctl net.core.somaxconn 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return {"server": server_name, "system_limits": lines}

@tool
def check_disk_smart(server_name: str = "local") -> dict:
    """Check disk health using SMART data.
    Use when asked: disk health, SMART data, is disk failing, disk errors, hardware health
    server_name: local, dev, or test
    """
    out = _run(server_name, "smartctl -H /dev/sda 2>/dev/null || smartctl -H /dev/nvme0 2>/dev/null || echo 'SMART not available'")
    healthy = "PASSED" in out or "OK" in out
    return {
        "server": server_name,
        "healthy": healthy,
        "status": "PASSED" if healthy else "FAILED or unavailable",
        "raw": [l.strip() for l in out.splitlines() if l.strip()][:10],
    }

@tool
def get_swap_activity(server_name: str = "local") -> dict:
    """Get swap memory activity — detect memory thrashing.
    Use when asked: swap usage, is server swapping, memory thrashing, swap in out
    server_name: local, dev, or test
    """
    out = _run(server_name, "vmstat 1 3 2>/dev/null | tail -3 && free -h 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    vmstat_lines = [l for l in lines if l[0].isdigit()]
    swapping = False
    if vmstat_lines:
        parts = vmstat_lines[-1].split()
        if len(parts) >= 8:
            si = int(parts[6]) if parts[6].isdigit() else 0
            so = int(parts[7]) if parts[7].isdigit() else 0
            swapping = si > 0 or so > 0
    return {
        "server": server_name,
        "swapping": swapping,
        "status": "THRASHING - high swap activity" if swapping else "Normal - no swap activity",
        "vmstat": vmstat_lines,
        "interpretation": "Server is using swap memory heavily — RAM is insufficient" if swapping else "RAM is sufficient — no swapping detected"
    }
