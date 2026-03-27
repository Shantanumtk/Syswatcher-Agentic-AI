import subprocess
from langchain_core.tools import tool
import os
import paramiko

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
def tail_log_file(path: str, lines: int = 50, server_name: str = "local") -> list:
    """Read the last N lines from a log file.
    Use when asked: show logs, tail log file, last lines of log
    path: full path to log file
    lines: number of lines (default 50)
    server_name: local, dev, or test
    """
    lines = min(lines, 200)
    out = _run(server_name, f"tail -{lines} {path} 2>&1")
    if "No such file" in out:
        return [f"File not found: {path}"]
    return [l for l in out.splitlines() if l.strip()]

@tool
def search_log_pattern(path: str, pattern: str, lines: int = 50, server_name: str = "local") -> list:
    """Search a log file for a pattern (grep).
    Use when asked: find errors in log, search for X in log, grep log
    path: log file path
    pattern: search term e.g. ERROR, connection refused, 500
    server_name: local, dev, or test
    """
    out = _run(server_name, f"grep -i '{pattern}' {path} 2>&1 | tail -{lines}")
    if "No such file" in out:
        return [f"File not found: {path}"]
    results = [l for l in out.splitlines() if l.strip()]
    return results if results else [f"No matches for '{pattern}' in {path}"]

@tool
def get_auth_failures(server_name: str = "local", hours_back: int = 24) -> list:
    """Get recent authentication failures from auth logs.
    Use when asked: auth failures, failed logins, SSH attacks, brute force
    server_name: local, dev, or test
    """
    out = _run(server_name, "grep -i 'failed\|invalid\|authentication failure' /var/log/auth.log 2>/dev/null | tail -50 || journalctl _SYSTEMD_UNIT=sshd.service --no-pager -n 50 -p warning 2>/dev/null")
    results = [l.strip() for l in out.splitlines() if l.strip()]
    return results if results else ["No auth failures found"]

@tool
def get_error_summary(server_name: str = "local", log_path: str = "/var/log/syslog") -> dict:
    """Get a summary of errors grouped by type and count.
    Use when asked: error summary, what errors are happening, group errors, error analysis
    server_name: local, dev, or test
    log_path: log file to analyze (default: /var/log/syslog)
    """
    out = _run(server_name, f"grep -i 'error\|critical\|fatal\|panic' {log_path} 2>/dev/null | tail -200")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    error_counts = {}
    for line in lines:
        words = line.split()
        key = " ".join(words[4:8]) if len(words) >= 8 else line[:60]
        error_counts[key] = error_counts.get(key, 0) + 1
    sorted_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    return {
        "server": server_name,
        "log_path": log_path,
        "total_errors": len(lines),
        "unique_error_types": len(error_counts),
        "top_errors": [{"pattern": k, "count": v} for k, v in sorted_errors],
    }

@tool
def get_oom_events(server_name: str = "local") -> list:
    """Get Out Of Memory (OOM) killer events — processes killed due to low memory.
    Use when asked: OOM events, out of memory, process killed by kernel, memory killer
    server_name: local, dev, or test
    """
    out = _run(server_name, "grep -i 'oom\|out of memory\|killed process' /var/log/syslog 2>/dev/null | tail -20 || dmesg 2>/dev/null | grep -i 'oom\|killed' | tail -20")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No OOM events found — memory is healthy"]

@tool
def get_kernel_messages(server_name: str = "local", limit: int = 30) -> list:
    """Get kernel messages (dmesg) — hardware errors, driver issues, OOM events.
    Use when asked: kernel messages, hardware errors, dmesg, kernel logs, system errors
    server_name: local, dev, or test
    """
    out = _run(server_name, f"dmesg --time-format iso 2>/dev/null | tail -{limit} || dmesg | tail -{limit}")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No kernel messages available"]

@tool
def get_application_errors(server_name: str = "local", pattern: str = "error", logs: list = None) -> dict:
    """Search multiple log files simultaneously for errors.
    Use when asked: application errors, search all logs, find errors across logs, multi-log search
    server_name: local, dev, or test
    pattern: error pattern to search (default: error)
    logs: list of log paths (default: common log locations)
    """
    if not logs:
        logs = ["/var/log/syslog", "/var/log/nginx/error.log", "/var/log/apache2/error.log", "/var/log/auth.log"]
    results = {}
    for log_path in logs:
        out = _run(server_name, f"grep -i '{pattern}' {log_path} 2>/dev/null | tail -10")
        lines = [l.strip() for l in out.splitlines() if l.strip() and "No such file" not in l]
        if lines:
            results[log_path] = lines
    return {"server": server_name, "pattern": pattern, "results": results, "total_matches": sum(len(v) for v in results.values())}

@tool
def get_log_volume_trend(server_name: str = "local", log_path: str = "/var/log/syslog") -> dict:
    """Check how fast a log file is growing — detect log explosion.
    Use when asked: log growth, log size, log explosion, disk filling from logs
    server_name: local, dev, or test
    log_path: log file to check
    """
    out = _run(server_name, f"ls -lh {log_path} 2>/dev/null && wc -l {log_path} 2>/dev/null && stat -c '%s %y' {log_path} 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return {"server": server_name, "log_path": log_path, "info": lines}

@tool
def get_segfault_events(server_name: str = "local") -> list:
    """Get segmentation fault events — application crashes.
    Use when asked: segfaults, application crashes, core dumps, process crashes
    server_name: local, dev, or test
    """
    out = _run(server_name, "grep -i 'segfault\|segmentation fault\|core dump' /var/log/syslog 2>/dev/null | tail -20 || dmesg 2>/dev/null | grep -i 'segfault' | tail -20")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No segfault events found"]
