from tools.system_tools import (
    get_cpu_stats, get_memory_stats, get_disk_usage,
    get_network_stats, get_top_processes, get_system_uptime,
    get_load_average, get_open_ports,
)
from tools.cron_tools import (
    get_cron_jobs, get_cron_logs, get_failed_crons,
    create_cron_job, delete_cron_job,
)
from tools.process_tools import (
    get_process_by_name, get_zombie_processes,
)
from tools.log_tools import (
    tail_log_file, search_log_pattern, get_auth_failures,
)
from tools.prometheus_tools import (
    query_prometheus_instant, query_prometheus_range,
    get_prometheus_alerts,
)
from tools.grafana_tools import (
    post_grafana_annotation, get_grafana_annotations,
)
from tools.alert_rules_tools import (
    create_alert_rule, list_alert_rules, remove_alert_rule,
)
from tools.notification_tools import (
    send_slack_alert, send_email_alert,
)

TOOL_GROUPS: dict[str, list] = {
    "system": [
        get_cpu_stats, get_memory_stats, get_disk_usage,
        get_network_stats, get_top_processes, get_system_uptime,
        get_load_average, get_open_ports,
    ],
    "cron": [
        get_cron_jobs, get_cron_logs, get_failed_crons,
        create_cron_job, delete_cron_job,
    ],
    "process": [
        get_process_by_name, get_zombie_processes,
    ],
    "logs": [
        tail_log_file, search_log_pattern, get_auth_failures,
    ],
    "prometheus": [
        query_prometheus_instant, query_prometheus_range,
        get_prometheus_alerts,
    ],
    "grafana": [
        post_grafana_annotation, get_grafana_annotations,
    ],
    "alerts": [
        create_alert_rule, list_alert_rules, remove_alert_rule,
    ],
    "notification": [
        send_slack_alert, send_email_alert,
    ],
}

# Always loaded — lightweight, needed for every question
ALWAYS_ON: list = (
    TOOL_GROUPS["system"]
    + TOOL_GROUPS["notification"]
    + TOOL_GROUPS["alerts"]
)

def get_tools_for_intent(intents: list[str]) -> list:
    seen = set()
    tools = []
    for t in ALWAYS_ON:
        if t.name not in seen:
            tools.append(t)
            seen.add(t.name)
    for intent in intents:
        for t in TOOL_GROUPS.get(intent, []):
            if t.name not in seen:
                tools.append(t)
                seen.add(t.name)
    return tools

def get_all_tools() -> list:
    seen = set()
    tools = []
    for group in TOOL_GROUPS.values():
        for t in group:
            if t.name not in seen:
                tools.append(t)
                seen.add(t.name)
    return tools
