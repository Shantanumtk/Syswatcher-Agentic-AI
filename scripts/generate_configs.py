#!/usr/bin/env python3
"""
Reads syswatcher.conf → generates .env + prometheus/prometheus.yml
"""
import re

CONF_FILE = "syswatcher.conf"

def parse_conf(path):
    servers  = {}
    settings = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                key  = key.strip()
                val  = val.strip()
                parts = val.split()
                if len(parts) == 3 and re.match(r"\d+\.\d+\.\d+\.\d+", parts[0]):
                    servers[key] = {
                        "ip":   parts[0],
                        "user": parts[1],
                        "key":  parts[2],
                    }
                else:
                    settings[key] = val
    return servers, settings

servers, s = parse_conf(CONF_FILE)

pg_user = s.get("POSTGRES_USER", "syswatcher")
pg_pass = s.get("POSTGRES_PASSWORD", "syswatcher123")
pg_db   = s.get("POSTGRES_DB", "syswatcher")

with open(".env", "w") as f:
    f.write("# Generated from syswatcher.conf — do not edit manually\n\n")

    # LLM
    f.write(f"OPENAI_API_KEY={s.get('OPENAI_API_KEY', '')}\n")
    f.write(f"LLM_MODEL={s.get('LLM_MODEL', 'gpt-4o-mini')}\n\n")

    # Postgres
    f.write(f"POSTGRES_HOST=postgres\n")
    f.write(f"POSTGRES_PORT=5432\n")
    f.write(f"POSTGRES_USER={pg_user}\n")
    f.write(f"POSTGRES_PASSWORD={pg_pass}\n")
    f.write(f"POSTGRES_DB={pg_db}\n")
    f.write(
        f"DATABASE_URL=postgresql://{pg_user}:{pg_pass}"
        f"@postgres:5432/{pg_db}\n\n"
    )

    # Observability
    f.write(f"PROMETHEUS_URL=http://prometheus:9090\n")
    f.write(f"GRAFANA_URL=http://grafana:3000\n")
    f.write(f"GRAFANA_TOKEN=\n\n")

    # Notifications
    f.write(f"SLACK_WEBHOOK_URL={s.get('SLACK_WEBHOOK_URL', '')}\n")
    f.write(f"ALERT_EMAIL_TO={s.get('ALERT_EMAIL_TO', '')}\n")
    f.write(f"SMTP_HOST={s.get('SMTP_HOST', 'smtp.gmail.com')}\n")
    f.write(f"SMTP_PORT={s.get('SMTP_PORT', '587')}\n")
    f.write(f"SMTP_USER={s.get('SMTP_USER', '')}\n")
    f.write(f"SMTP_PASSWORD={s.get('SMTP_PASSWORD', '')}\n\n")

    # Sweep + thresholds
    f.write(f"SWEEP_INTERVAL_MIN={s.get('SWEEP_INTERVAL_MIN', '5')}\n")
    f.write(f"CRITICAL_CPU_PCT={s.get('CRITICAL_CPU_PCT', '98')}\n")
    f.write(f"CRITICAL_MEMORY_PCT={s.get('CRITICAL_MEMORY_PCT', '95')}\n")
    f.write(f"CRITICAL_DISK_PCT={s.get('CRITICAL_DISK_PCT', '95')}\n")
    f.write(f"CRITICAL_CRON_FAILS={s.get('CRITICAL_CRON_FAILS', '3')}\n\n")

    # Grafana
    f.write(
        f"GRAFANA_ADMIN_PASSWORD="
        f"{s.get('GRAFANA_ADMIN_PASSWORD', 'admin123')}\n"
    )

    # Ports
    f.write(f"API_PORT={s.get('API_PORT', '8000')}\n")
    f.write(f"UI_PORT={s.get('UI_PORT', '3001')}\n\n")

    # Servers list (for scheduler)
    server_names = list(servers.keys())
    f.write(f"SERVERS={','.join(server_names) if server_names else 'local'}\n\n")

    # Per-server IP vars (for scheduler registration)
    for name, srv in servers.items():
        env_key = f"SERVER_{name.upper().replace('-', '_')}_IP"
        f.write(f"{env_key}={srv['ip']}\n")

print("✓ .env generated")

# Prometheus scrape config
prom = [
    "global:",
    "  scrape_interval: 15s",
    "  evaluation_interval: 15s",
    "",
    "scrape_configs:",
    "  - job_name: local",
    "    static_configs:",
    '      - targets: ["node_exporter:9100"]',
    "        labels:",
    "          server_name: local",
]

for name, srv in servers.items():
    prom += [
        f"  - job_name: {name}",
        f"    static_configs:",
        f'      - targets: ["{srv["ip"]}:9100"]',
        f"        labels:",
        f"          server_name: {name}",
    ]

with open("prometheus/prometheus.yml", "w") as f:
    f.write("\n".join(prom) + "\n")

print(f"✓ prometheus.yml generated ({len(servers)} remote server(s))")
print("✓ Done")
