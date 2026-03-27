import os
import subprocess
import paramiko
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
def get_failed_ssh_attempts(server_name: str = "local", limit: int = 20) -> list:
    """Get recent failed SSH login attempts — detect brute force attacks.
    Use when asked: SSH attacks, brute force, failed logins, who tried to login, unauthorized access
    server_name: local, dev, or test
    limit: number of recent attempts to return
    """
    out = _run(server_name, f"grep 'Failed password\|Invalid user\|authentication failure' /var/log/auth.log 2>/dev/null | tail -{limit} || journalctl _SYSTEMD_UNIT=sshd.service -n {limit} --no-pager -p warning 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No failed SSH attempts found"]

@tool
def get_active_sessions(server_name: str = "local") -> list:
    """Get currently logged in users and their sessions.
    Use when asked: who is logged in, active sessions, current users, who is on the server
    server_name: local, dev, or test
    """
    out = _run(server_name, "who && echo '---' && last -n 5 2>/dev/null | head -10")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No active sessions found"]

@tool
def get_sudo_history(server_name: str = "local", limit: int = 20) -> list:
    """Get recent sudo command usage — audit privileged operations.
    Use when asked: sudo history, privileged commands, what sudo commands were run, admin activity
    server_name: local, dev, or test
    """
    out = _run(server_name, f"grep 'sudo' /var/log/auth.log 2>/dev/null | tail -{limit} || journalctl _COMM=sudo -n {limit} --no-pager 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No sudo history found"]

@tool
def get_firewall_rules(server_name: str = "local") -> dict:
    """Get active firewall rules (UFW or iptables).
    Use when asked: firewall rules, open ports in firewall, UFW rules, iptables rules, what is blocked
    server_name: local, dev, or test
    """
    ufw = _run(server_name, "ufw status numbered 2>/dev/null || echo 'UFW not available'")
    iptables = _run(server_name, "iptables -L INPUT -n --line-numbers 2>/dev/null | head -30 || echo 'iptables not available'")
    return {
        "server": server_name,
        "ufw": [l.strip() for l in ufw.splitlines() if l.strip()],
        "iptables_input": [l.strip() for l in iptables.splitlines() if l.strip()],
    }

@tool
def get_ssl_cert_expiry(server_name: str = "local", domains: list = None) -> list:
    """Check SSL certificate expiry dates for domains or local certs.
    Use when asked: SSL cert expiry, certificate expiry, when does cert expire, SSL check
    server_name: local, dev, or test
    domains: list of domains to check (optional)
    """
    results = []
    if domains:
        for domain in domains:
            out = _run(server_name, f"echo | openssl s_client -servername {domain} -connect {domain}:443 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null")
            results.append({"domain": domain, "expiry": out.strip() or "Could not check"})
    else:
        out = _run(server_name, "find /etc/ssl /etc/nginx /etc/letsencrypt -name '*.crt' -o -name '*.pem' 2>/dev/null | head -10 | xargs -I{} openssl x509 -noout -enddate -subject -in {} 2>/dev/null")
        results = [{"cert": l.strip()} for l in out.splitlines() if l.strip()] or [{"info": "No SSL certs found in standard locations"}]
    return results

@tool
def get_listening_services(server_name: str = "local") -> list:
    """Get all services listening on network ports with process ownership.
    Use when asked: what services are running, listening services, what is on port X, service audit
    server_name: local, dev, or test
    """
    out = _run(server_name, "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip() and "LISTEN" in l]
    parsed = []
    for line in lines:
        parts = line.split()
        parsed.append({"local_address": parts[3] if len(parts) > 3 else "", "process": parts[-1] if parts else "", "raw": line})
    return parsed if parsed else [{"info": "No listening services found"}]

@tool
def get_recent_logins(server_name: str = "local", limit: int = 10) -> list:
    """Get recent successful login history.
    Use when asked: recent logins, login history, who logged in, last logins
    server_name: local, dev, or test
    """
    out = _run(server_name, f"last -n {limit} --time-format iso 2>/dev/null | head -{limit+2}")
    lines = [l.strip() for l in out.splitlines() if l.strip() and "wtmp" not in l]
    return lines if lines else ["No login history found"]

@tool
def get_world_writable_files(server_name: str = "local") -> list:
    """Find world-writable files and directories — security misconfiguration risk.
    Use when asked: world writable files, security scan, file permissions, insecure files
    server_name: local, dev, or test
    """
    out = _run(server_name, "find /etc /usr /var -maxdepth 3 -perm -o+w -not -path '*/proc/*' 2>/dev/null | head -20", timeout=15)
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No world-writable files found in standard locations — good"]

@tool
def get_failed_services(server_name: str = "local") -> list:
    """Get all failed systemd services.
    Use when asked: failed services, what services crashed, broken services, systemd failures
    server_name: local, dev, or test
    """
    out = _run(server_name, "systemctl --failed --no-legend 2>/dev/null | head -20")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No failed services — all services are running"]

@tool
def get_service_status(server_name: str = "local", service: str = "nginx") -> dict:
    """Check status of a specific systemd service.
    Use when asked: is nginx running, check apache status, is postgres up, service health check
    server_name: local, dev, or test
    service: service name e.g. nginx, apache2, postgresql, redis, docker
    """
    out = _run(server_name, f"systemctl is-active {service} 2>/dev/null && systemctl status {service} --no-pager -l 2>/dev/null | head -20")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    active = "active" in (lines[0] if lines else "")
    return {"server": server_name, "service": service, "active": active, "status": lines[0] if lines else "unknown", "details": lines[1:10]}
