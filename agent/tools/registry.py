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
    get_error_summary, get_oom_events, get_kernel_messages,
    get_application_errors, get_log_volume_trend, get_segfault_events,
)
from tools.prometheus_tools import (
    query_prometheus_instant, query_prometheus_range,
    get_prometheus_alerts, get_cpu_trend, get_memory_trend,
    get_disk_io_rate, get_network_bandwidth, get_cpu_iowait,
    compare_server_metrics, get_prometheus_targets, get_metric_anomaly,
)
from tools.grafana_tools import (
    post_grafana_annotation, get_grafana_annotations,
    get_annotations_timeline, get_grafana_dashboard_list,
    get_grafana_health,
)
from tools.rca_tools import (
    get_rca_report, get_system_baseline,
)
from tools.security_tools import (
    get_failed_ssh_attempts, get_active_sessions, get_sudo_history,
    get_firewall_rules, get_ssl_cert_expiry, get_listening_services,
    get_recent_logins, get_world_writable_files, get_failed_services,
    get_service_status,
)
from tools.application_tools import (
    check_port_open, check_url_health, check_process_alive,
    get_docker_containers, get_docker_stats, get_service_logs,
    get_environment_check, check_disk_smart, get_swap_activity,
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
        get_load_average, get_open_ports, get_swap_activity,
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
        get_error_summary, get_oom_events, get_kernel_messages,
        get_application_errors, get_log_volume_trend, get_segfault_events,
    ],
    "prometheus": [
        query_prometheus_instant, query_prometheus_range,
        get_prometheus_alerts, get_cpu_trend, get_memory_trend,
        get_disk_io_rate, get_network_bandwidth, get_cpu_iowait,
        compare_server_metrics, get_prometheus_targets, get_metric_anomaly,
    ],
    "grafana": [
        post_grafana_annotation, get_grafana_annotations,
        get_annotations_timeline, get_grafana_dashboard_list,
        get_grafana_health,
    ],
    "rca": [
        get_rca_report, get_system_baseline,
    ],
    "security": [
        get_failed_ssh_attempts, get_active_sessions, get_sudo_history,
        get_firewall_rules, get_ssl_cert_expiry, get_listening_services,
        get_recent_logins, get_world_writable_files, get_failed_services,
        get_service_status,
    ],
    "application": [
        check_port_open, check_url_health, check_process_alive,
        get_docker_containers, get_docker_stats, get_service_logs,
        get_environment_check, check_disk_smart,
    ],
    "alerts": [
        create_alert_rule, list_alert_rules, remove_alert_rule,
    ],
    "notification": [
        send_slack_alert, send_email_alert,
    ],
}

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
