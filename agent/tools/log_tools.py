import subprocess
from langchain_core.tools import tool

def _run(cmd: str, timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr
    except Exception as e:
        return str(e)

@tool
def tail_log_file(path: str, lines: int = 50) -> list:
    """Read the last N lines from a log file.
    Use when asked: 'show logs', 'tail /var/log/app.log', 'last 100 lines of nginx log'
    path:  full path to log file e.g. /var/log/nginx/error.log
    lines: number of lines to return (default 50, max 200)
    """
    lines = min(lines, 200)
    out = _run(f"tail -{lines} {path} 2>&1")
    if "No such file" in out:
        return [f"File not found: {path}"]
    return [l for l in out.splitlines() if l.strip()]

@tool
def search_log_pattern(path: str, pattern: str, lines: int = 50) -> list:
    """Search a log file for a pattern (grep).
    Use when asked: 'find errors in log', 'search for X in /var/log/app.log',
    'grep ERROR in syslog'
    path:    full log file path
    pattern: search term or regex e.g. 'ERROR', 'connection refused', '500'
    lines:   max results to return (default 50)
    """
    out = _run(f"grep -i '{pattern}' {path} 2>&1 | tail -{lines}")
    if "No such file" in out:
        return [f"File not found: {path}"]
    results = [l for l in out.splitlines() if l.strip()]
    return results if results else [f"No matches for '{pattern}' in {path}"]

@tool
def get_auth_failures(hours_back: int = 24) -> list:
    """Get recent authentication failures from auth logs.
    Use when asked: 'auth failures', 'failed logins', 'SSH attacks', 'brute force'
    hours_back: how many hours to look back (default 24)
    """
    # Try auth.log first, then secure, then journalctl
    out = _run(f"grep -i 'failed\\|invalid\\|authentication failure' /var/log/auth.log 2>/dev/null | tail -50")
    if not out.strip():
        out = _run("grep -i 'failed\\|invalid' /var/log/secure 2>/dev/null | tail -50")
    if not out.strip():
        out = _run("journalctl _SYSTEMD_UNIT=sshd.service --no-pager -n 50 -p warning 2>/dev/null")

    results = [l.strip() for l in out.splitlines() if l.strip()]
    return results if results else ["No auth failures found in logs"]
