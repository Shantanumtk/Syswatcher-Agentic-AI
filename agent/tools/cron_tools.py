import subprocess
import paramiko
import os
from langchain_core.tools import tool
from db import queries
import asyncio

def _run_local(cmd: str, timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr
    except Exception as e:
        return str(e)

def _get_server_ssh(server_name: str) -> tuple:
    """Get SSH connection details for a server from DB."""
    def _fetch():
        return asyncio.run(queries.get_servers())
    try:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            servers = pool.submit(_fetch).result(timeout=10)
        for s in servers:
            if s["name"] == server_name:
                return s.get("ip"), s.get("ssh_user", "ubuntu"), s.get("ssh_key_path", "")
    except Exception:
        pass
    return None, None, None

def _run_ssh(server_name: str, cmd: str, timeout: int = 8) -> str:
    """Run a command on a remote server via SSH."""
    ip, user, key_path = _get_server_ssh(server_name)
    if not ip:
        return f"Server '{server_name}' not found in database"
    if not key_path or not os.path.exists(key_path):
        return f"SSH key not found: {key_path}"
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=user, key_filename=key_path, timeout=6, banner_timeout=6)
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode() + stderr.read().decode()
        client.close()
        return out
    except Exception as e:
        return f"SSH error: {e}"

def _run_on_server(server_name: str, cmd: str) -> str:
    """Run command locally if local server, SSH otherwise."""
    if server_name in ("local", "localhost", ""):
        return _run_local(cmd)
    return _run_ssh(server_name, cmd)

@tool
def get_cron_jobs(server_name: str = "local") -> list:
    """Get all cron jobs configured on a server.
    Use when asked: 'what crons are configured?', 'show cron jobs', 'list crons'
    server_name: which server to check (default: local)
    """
    jobs = []

    # current user crontab
    out = _run_on_server(server_name, "crontab -l 2>/dev/null || echo ''")
    for line in out.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            jobs.append({"user": "ubuntu", "source": "crontab", "entry": line})

    # /etc/cron.d/
    out = _run_on_server(server_name, "ls /etc/cron.d/ 2>/dev/null || echo ''")
    for fname in out.splitlines():
        fname = fname.strip()
        if not fname:
            continue
        content = _run_on_server(server_name, f"cat /etc/cron.d/{fname} 2>/dev/null")
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and len(line.split()) >= 6:
                jobs.append({"source": f"/etc/cron.d/{fname}", "entry": line})

    return jobs if jobs else [{"info": "No cron jobs found"}]

@tool
def get_cron_logs(server_name: str = "local", filter_keyword: str = "", lines: int = 50) -> list:
    """Get recent cron execution logs.
    Use when asked: 'did cron run?', 'cron logs', 'did backup cron run?'
    server_name: which server to check
    filter_keyword: optional keyword to filter e.g. 'backup'
    lines: number of log lines to return
    """
    cmd = f"grep -i CRON /var/log/syslog 2>/dev/null | tail -{lines}"
    raw = _run_on_server(server_name, cmd)
    if not raw.strip():
        raw = _run_on_server(server_name, f"journalctl -u cron --no-pager -n {lines} 2>/dev/null")

    entries = []
    for line in raw.splitlines():
        if filter_keyword and filter_keyword.lower() not in line.lower():
            continue
        if line.strip():
            entries.append(line.strip())

    return entries if entries else [f"No cron logs found (filter: '{filter_keyword}')"]

@tool
def get_failed_crons(server_name: str = "local", hours_back: int = 24) -> list:
    """Get cron jobs that failed recently.
    Use when asked: 'did any crons fail?', 'failed cron jobs', 'cron errors'
    server_name: which server to check
    hours_back: how many hours of history to check
    """
    cmd = "grep -i 'CRON.*error\\|CRON.*fail\\|exit.*[1-9]' /var/log/syslog 2>/dev/null | tail -50"
    raw = _run_on_server(server_name, cmd)
    if not raw.strip():
        raw = _run_on_server(server_name, "journalctl -u cron --no-pager -n 100 -p err 2>/dev/null")

    failures = [line.strip() for line in raw.splitlines() if line.strip()]
    return failures if failures else ["No cron failures found in logs"]

@tool
def create_cron_job(
    schedule: str,
    command: str,
    name: str,
    server_name: str = "local",
    log_path: str = "",
) -> dict:
    """Create a new cron job on a server via SSH.
    Use when asked: 'add a cron', 'schedule a task', 'create a cron job'
    schedule:    cron expression e.g. '* * * * *' (every minute), '0 2 * * *' (2am daily)
    command:     command to run e.g. 'echo hello', '/opt/scripts/backup.sh'
    name:        friendly name e.g. 'test_hello', 'db_backup'
    server_name: which server (default: local)
    log_path:    optional log file e.g. '/tmp/test.log'

    Common schedules:
      Every minute  : * * * * *
      Every hour    : 0 * * * *
      Daily at 2am  : 0 2 * * *
      Every Sunday  : 0 0 * * 0
    """
    if len(schedule.split()) != 5:
        return {"success": False, "error": f"Invalid schedule '{schedule}' — must be 5-part cron expression"}

    if log_path:
        entry = f"{schedule} {command} >> {log_path} 2>&1"
    else:
        entry = f"{schedule} {command}"

    comment = f"# syswatcher:{name}"

    # Read current crontab
    current = _run_on_server(server_name, "crontab -l 2>/dev/null || echo ''")

    if f"syswatcher:{name}" in current:
        return {"success": False, "error": f"Cron '{name}' already exists. Delete it first."}

    new_crontab = current.rstrip("\n") + f"\n{comment}\n{entry}\n"

    # Write new crontab via SSH
    if server_name in ("local", "localhost", ""):
        import subprocess
        proc = subprocess.run("crontab -", input=new_crontab, shell=True, capture_output=True, text=True)
        if proc.returncode != 0:
            return {"success": False, "error": proc.stderr or "crontab command failed — not available in container"}
    else:
        ip, user, key_path = _get_server_ssh(server_name)
        if not ip:
            return {"success": False, "error": f"Server '{server_name}' not found"}
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(ip, username=user, key_filename=key_path, timeout=6, banner_timeout=6)
            _, stdout, stderr = client.exec_command(f"echo '{new_crontab}' | crontab -")
            err = stderr.read().decode()
            client.close()
            if err:
                return {"success": False, "error": err}
        except Exception as e:
            return {"success": False, "error": str(e)}

    return {
        "success":  True,
        "name":     name,
        "schedule": schedule,
        "command":  command,
        "server":   server_name,
        "log_path": log_path,
        "entry":    entry,
        "message":  f"Cron '{name}' created on {server_name} — runs: {schedule}",
    }

@tool
def delete_cron_job(name: str, server_name: str = "local") -> dict:
    """Delete a cron job created by SysWatcher.
    Use when asked: 'remove cron', 'delete cron job', 'stop the backup cron'
    name:        the friendly name used when creating e.g. 'db_backup'
    server_name: which server
    """
    current = _run_on_server(server_name, "crontab -l 2>/dev/null || echo ''")

    if f"syswatcher:{name}" not in current:
        return {"success": False, "error": f"Cron '{name}' not found on {server_name}"}

    new_lines = []
    skip_next = False
    for line in current.splitlines():
        if f"syswatcher:{name}" in line:
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        new_lines.append(line)

    new_crontab = "\n".join(new_lines) + "\n"

    if server_name in ("local", "localhost", ""):
        import subprocess
        proc = subprocess.run("crontab -", input=new_crontab, shell=True, capture_output=True, text=True)
        if proc.returncode != 0:
            return {"success": False, "error": proc.stderr}
    else:
        ip, user, key_path = _get_server_ssh(server_name)
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(ip, username=user, key_filename=key_path, timeout=6, banner_timeout=6)
            _, stdout, stderr = client.exec_command(f"echo '{new_crontab}' | crontab -")
            client.close()
        except Exception as e:
            return {"success": False, "error": str(e)}

    return {"success": True, "message": f"Cron '{name}' deleted from {server_name}"}
