import subprocess
import re
from datetime import datetime
from langchain_core.tools import tool

def _run(cmd: str, timeout: int = 10) -> str:
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, timeout=timeout
        )
        return r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return "command timed out"
    except Exception as e:
        return str(e)

@tool
def get_cron_jobs() -> list:
    """Get all cron jobs configured on this system for all users.
    Use when asked: 'what crons are configured?', 'show cron jobs',
    'what scheduled tasks exist?', 'list crons'
    """
    jobs = []

    # current user crontab
    out = _run("crontab -l 2>/dev/null")
    for line in out.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            jobs.append({"user": "current", "entry": line})

    # /etc/cron.d/
    out = _run("ls /etc/cron.d/ 2>/dev/null")
    for fname in out.splitlines():
        content = _run(f"cat /etc/cron.d/{fname} 2>/dev/null")
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and len(line.split()) >= 6:
                jobs.append({"source": f"/etc/cron.d/{fname}", "entry": line})

    # /etc/crontab
    out = _run("cat /etc/crontab 2>/dev/null")
    for line in out.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and len(line.split()) >= 7:
            jobs.append({"source": "/etc/crontab", "entry": line})

    return jobs if jobs else [{"info": "No cron jobs found"}]

@tool
def get_cron_logs(filter_keyword: str = "", lines: int = 50) -> list:
    """Get recent cron execution logs from syslog.
    Use when asked: 'did cron run?', 'cron logs', 'did backup cron run last night?'
    filter_keyword: optional keyword to filter e.g. 'backup', 'logrotate'
    lines: number of log lines to return (default 50)
    """
    raw = _run(f"grep -i CRON /var/log/syslog 2>/dev/null | tail -{lines}")
    if not raw.strip():
        raw = _run(f"journalctl -u cron --no-pager -n {lines} 2>/dev/null")

    entries = []
    for line in raw.splitlines():
        if filter_keyword and filter_keyword.lower() not in line.lower():
            continue
        entries.append(line.strip())

    return entries if entries else [f"No cron logs found (filter: '{filter_keyword}')"]

@tool
def get_failed_crons(hours_back: int = 24) -> list:
    """Get cron jobs that failed recently (non-zero exit codes in logs).
    Use when asked: 'did any crons fail?', 'failed cron jobs', 'cron errors'
    hours_back: how many hours of history to check (default 24)
    """
    raw = _run(f"grep -i 'CRON.*error\\|CRON.*fail\\|exit.*[1-9]' /var/log/syslog 2>/dev/null | tail -50")
    if not raw.strip():
        raw = _run("journalctl -u cron --no-pager -n 100 -p err 2>/dev/null")

    failures = [line.strip() for line in raw.splitlines() if line.strip()]
    return failures if failures else ["No cron failures found in logs"]

@tool
def create_cron_job(
    schedule: str,
    command: str,
    name: str,
    log_path: str = "",
) -> dict:
    """Create a new cron job on the system.
    Use when asked: 'add a cron', 'schedule a task', 'create a cron job'
    schedule: cron expression e.g. '0 2 * * *' (2am daily)
              or natural: 'every day at 2am' -> '0 2 * * *'
    command:  full command path e.g. '/opt/scripts/backup.sh'
    name:     friendly name for tracking e.g. 'db_backup'
    log_path: optional log file e.g. '/var/log/backup.log'

    Common schedule expressions:
      Every minute       : * * * * *
      Every hour         : 0 * * * *
      Daily at 2am       : 0 2 * * *
      Every Sunday midnt : 0 0 * * 0
      Every 6 hours      : 0 */6 * * *
      Weekdays at 9am    : 0 9 * * 1-5
    """
    # Validate schedule has 5 parts
    if len(schedule.split()) != 5:
        return {
            "success": False,
            "error": f"Invalid schedule '{schedule}' — must be 5-part cron expression e.g. '0 2 * * *'"
        }

    # Build cron entry
    if log_path:
        entry = f"{schedule} {command} >> {log_path} 2>&1"
    else:
        entry = f"{schedule} {command}"

    comment = f"# syswatcher:{name}"

    # Read current crontab
    current = _run("crontab -l 2>/dev/null")
    if f"syswatcher:{name}" in current:
        return {"success": False, "error": f"Cron '{name}' already exists. Delete it first."}

    # Append new entry
    new_crontab = current.rstrip("\n") + f"\n{comment}\n{entry}\n"

    # Write back
    proc = subprocess.run(
        "crontab -", input=new_crontab,
        shell=True, capture_output=True, text=True
    )

    if proc.returncode != 0:
        return {"success": False, "error": proc.stderr}

    return {
        "success": True,
        "name":    name,
        "schedule": schedule,
        "command":  command,
        "log_path": log_path,
        "entry":    entry,
        "message":  f"Cron '{name}' created — runs: {schedule}",
    }

@tool
def delete_cron_job(name: str) -> dict:
    """Delete a cron job created by SysWatcher.
    Use when asked: 'remove cron', 'delete cron job', 'stop the backup cron'
    name: the friendly name used when creating e.g. 'db_backup'
    """
    current = _run("crontab -l 2>/dev/null")
    if f"syswatcher:{name}" not in current:
        return {"success": False, "error": f"Cron '{name}' not found"}

    # Filter out the comment and entry lines for this cron
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
    proc = subprocess.run(
        "crontab -", input=new_crontab,
        shell=True, capture_output=True, text=True
    )

    if proc.returncode != 0:
        return {"success": False, "error": proc.stderr}

    return {"success": True, "message": f"Cron '{name}' deleted"}
