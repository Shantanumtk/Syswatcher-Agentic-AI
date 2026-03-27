#!/usr/bin/env python3
import os
import json
import logging
import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request
from starlette.responses import JSONResponse
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [mcp] %(levelname)s - %(message)s")
logger = logging.getLogger("syswatcher.mcp")

API_URL = os.getenv("SYSWATCHER_API", "http://agent:8000")
API_KEY = os.getenv("MCP_API_KEY", "syswatcher123")

mcp = Server("syswatcher")


async def _ask(question: str, server_name: str = "local") -> str:
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{API_URL}/ask", json={"question": question, "server_name": server_name})
        r.raise_for_status()
        d = r.json()
        sev = d.get("severity", "healthy").upper()
        return f"[{sev}] {d.get('answer', '')}"


async def _api(method: str, path: str, body: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        if method == "GET":
            r = await client.get(f"{API_URL}{path}", params=body or {})
        elif method == "DELETE":
            r = await client.delete(f"{API_URL}{path}")
        else:
            r = await client.post(f"{API_URL}{path}", json=body or {})
        r.raise_for_status()
        return r.json()


def _t(data) -> list:
    if isinstance(data, (dict, list)):
        return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]
    return [TextContent(type="text", text=str(data))]


def _s(text: str) -> list:
    return [TextContent(type="text", text=text)]


@mcp.list_tools()
async def list_tools():
    return [
        # ── Core ─────────────────────────────────────────────
        Tool(name="ask_syswatcher", description="Ask SysWatcher anything in plain English about your servers", inputSchema={"type":"object","properties":{"question":{"type":"string"},"server_name":{"type":"string","default":"local"}},"required":["question"]}),
        Tool(name="run_sweep", description="Run a full health sweep on a server", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_server_status", description="Get quick health status — overall, critical/warn counts, last sweep", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="list_servers", description="List all monitored servers", inputSchema={"type":"object","properties":{}}),
        Tool(name="get_recent_events", description="Get recent health events", inputSchema={"type":"object","properties":{"server_name":{"type":"string"},"severity":{"type":"string"},"limit":{"type":"integer","default":20}}}),
        Tool(name="get_sweep_history", description="Get sweep history", inputSchema={"type":"object","properties":{"server_name":{"type":"string"},"limit":{"type":"integer","default":10}}}),

        # ── System ───────────────────────────────────────────
        Tool(name="get_cpu_stats", description="Get live CPU usage, per-core breakdown and load average", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_memory_stats", description="Get live RAM and swap usage", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_disk_usage", description="Get disk usage for a mount point", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"path":{"type":"string","default":"/"}}}),
        Tool(name="get_network_stats", description="Get network interface stats — bytes sent/received, errors", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_top_processes", description="Get top processes by CPU usage", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"limit":{"type":"integer","default":10}}}),
        Tool(name="get_system_uptime", description="Get system uptime and boot time", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_load_average", description="Get system load average for 1, 5, and 15 minutes", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_open_ports", description="Get list of open listening ports and which process owns them", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_swap_activity", description="Get swap memory activity — detect memory thrashing", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),

        # ── Cron ─────────────────────────────────────────────
        Tool(name="get_cron_jobs", description="List all cron jobs on a server", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_cron_logs", description="Get recent cron execution logs", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"filter_keyword":{"type":"string","default":""},"lines":{"type":"integer","default":50}}}),
        Tool(name="get_failed_crons", description="Get cron jobs that failed recently", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="create_cron_job", description="Create a new cron job on a server", inputSchema={"type":"object","properties":{"name":{"type":"string"},"schedule":{"type":"string"},"command":{"type":"string"},"server_name":{"type":"string","default":"local"},"log_path":{"type":"string"}},"required":["name","schedule","command"]}),
        Tool(name="delete_cron_job", description="Delete a cron job by name", inputSchema={"type":"object","properties":{"name":{"type":"string"},"server_name":{"type":"string","default":"local"}},"required":["name"]}),

        # ── Process ──────────────────────────────────────────
        Tool(name="get_process_by_name", description="Find running processes by name", inputSchema={"type":"object","properties":{"name":{"type":"string"},"server_name":{"type":"string","default":"local"}},"required":["name"]}),
        Tool(name="get_zombie_processes", description="Find zombie (defunct) processes", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),

        # ── Logs ─────────────────────────────────────────────
        Tool(name="tail_log_file", description="Read the last N lines from a log file", inputSchema={"type":"object","properties":{"path":{"type":"string"},"lines":{"type":"integer","default":50},"server_name":{"type":"string","default":"local"}},"required":["path"]}),
        Tool(name="search_log_pattern", description="Search a log file for a pattern (grep)", inputSchema={"type":"object","properties":{"path":{"type":"string"},"pattern":{"type":"string"},"lines":{"type":"integer","default":50},"server_name":{"type":"string","default":"local"}},"required":["path","pattern"]}),
        Tool(name="get_auth_failures", description="Get recent authentication failures from auth logs", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_error_summary", description="Get a summary of errors grouped by type and count", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"log_path":{"type":"string","default":"/var/log/syslog"}}}),
        Tool(name="get_oom_events", description="Get Out Of Memory killer events", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_kernel_messages", description="Get kernel messages (dmesg) — hardware errors, driver issues", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"limit":{"type":"integer","default":30}}}),
        Tool(name="get_application_errors", description="Search multiple log files simultaneously for errors", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"pattern":{"type":"string","default":"error"}}}),
        Tool(name="get_log_volume_trend", description="Check how fast a log file is growing — detect log explosion", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"log_path":{"type":"string","default":"/var/log/syslog"}}}),
        Tool(name="get_segfault_events", description="Get segmentation fault events — application crashes", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),

        # ── Prometheus ───────────────────────────────────────
        Tool(name="query_prometheus_instant", description="Query Prometheus for a current metric value using PromQL", inputSchema={"type":"object","properties":{"promql":{"type":"string"}},"required":["promql"]}),
        Tool(name="query_prometheus_range", description="Query Prometheus for metric history over a time range", inputSchema={"type":"object","properties":{"promql":{"type":"string"},"hours_back":{"type":"integer","default":1}},"required":["promql"]}),
        Tool(name="get_prometheus_alerts", description="Get all currently firing Prometheus alerts", inputSchema={"type":"object","properties":{}}),
        Tool(name="get_cpu_trend", description="Get CPU usage trend over time — detect spikes and patterns", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"hours_back":{"type":"integer","default":3}}}),
        Tool(name="get_memory_trend", description="Get memory usage trend — detect memory leaks", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"hours_back":{"type":"integer","default":3}}}),
        Tool(name="get_disk_io_rate", description="Get real-time disk read/write speed in MB/s", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_network_bandwidth", description="Get real-time network bandwidth in Mbps", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_cpu_iowait", description="Get CPU I/O wait percentage — is disk the bottleneck?", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="compare_server_metrics", description="Compare the same metric across all monitored servers", inputSchema={"type":"object","properties":{"metric":{"type":"string","default":"cpu","enum":["cpu","memory","disk","load","network"]}}}),
        Tool(name="get_prometheus_targets", description="Check which servers Prometheus is scraping and their health", inputSchema={"type":"object","properties":{}}),
        Tool(name="get_metric_anomaly", description="Detect sudden spikes or anomalies compared to recent baseline", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"metric":{"type":"string","default":"cpu","enum":["cpu","memory","disk","network"]}}}),

        # ── Grafana ──────────────────────────────────────────
        Tool(name="post_grafana_annotation", description="Post an annotation to Grafana marking a health event", inputSchema={"type":"object","properties":{"text":{"type":"string"},"severity":{"type":"string","default":"warn","enum":["info","warn","critical"]}},"required":["text"]}),
        Tool(name="get_grafana_annotations", description="Fetch recent SysWatcher annotations from Grafana", inputSchema={"type":"object","properties":{"hours_back":{"type":"integer","default":24}}}),
        Tool(name="get_annotations_timeline", description="Get a timeline of SysWatcher events for incident investigation", inputSchema={"type":"object","properties":{"hours_back":{"type":"integer","default":6},"server_name":{"type":"string"}}}),
        Tool(name="get_grafana_dashboard_list", description="List all available Grafana dashboards", inputSchema={"type":"object","properties":{}}),
        Tool(name="get_grafana_health", description="Check if Grafana is healthy and accessible", inputSchema={"type":"object","properties":{}}),

        # ── RCA ──────────────────────────────────────────────
        Tool(name="get_rca_report", description="Generate a full Root Cause Analysis report for a server", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"hours_back":{"type":"integer","default":2}}}),
        Tool(name="get_system_baseline", description="Compare current metrics against 24-hour baseline", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),

        # ── Security ─────────────────────────────────────────
        Tool(name="get_failed_ssh_attempts", description="Get recent failed SSH login attempts — detect brute force", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"limit":{"type":"integer","default":20}}}),
        Tool(name="get_active_sessions", description="Get currently logged in users and their sessions", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_sudo_history", description="Get recent sudo command usage — audit privileged operations", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"limit":{"type":"integer","default":20}}}),
        Tool(name="get_firewall_rules", description="Get active firewall rules (UFW or iptables)", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_ssl_cert_expiry", description="Check SSL certificate expiry dates", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"domains":{"type":"array","items":{"type":"string"}}}}),
        Tool(name="get_listening_services", description="Get all services listening on network ports", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_recent_logins", description="Get recent successful login history", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"limit":{"type":"integer","default":10}}}),
        Tool(name="get_world_writable_files", description="Find world-writable files — security misconfiguration risk", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_failed_services", description="Get all failed systemd services", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_service_status", description="Check status of a specific systemd service", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"service":{"type":"string","default":"nginx"}},"required":["service"]}),

        # ── Application ──────────────────────────────────────
        Tool(name="check_port_open", description="Check if a specific port is open and responding", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"port":{"type":"integer"},"host":{"type":"string","default":"localhost"}},"required":["port"]}),
        Tool(name="check_url_health", description="Check if a URL is healthy and returning expected status code", inputSchema={"type":"object","properties":{"url":{"type":"string"},"expected_status":{"type":"integer","default":200},"timeout":{"type":"integer","default":10}},"required":["url"]}),
        Tool(name="check_process_alive", description="Check if a named process is running", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"process_name":{"type":"string"}},"required":["process_name"]}),
        Tool(name="get_docker_containers", description="List all Docker containers and their status", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_docker_stats", description="Get Docker container resource usage (CPU, memory)", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_service_logs", description="Get recent logs from a systemd service using journalctl", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"service":{"type":"string"},"lines":{"type":"integer","default":50}},"required":["service"]}),
        Tool(name="get_environment_check", description="Check critical system configuration and limits", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="check_disk_smart", description="Check disk health using SMART data", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),

        # ── Alerts ───────────────────────────────────────────
        Tool(name="get_alert_rules", description="List all configured alert rules", inputSchema={"type":"object","properties":{"server_name":{"type":"string"}}}),
        Tool(name="create_alert", description="Create a new alert rule", inputSchema={"type":"object","properties":{"metric":{"type":"string"},"condition":{"type":"string","enum":["gt","lt","eq"]},"threshold":{"type":"number"},"severity":{"type":"string","enum":["warn","critical"]},"notify_slack":{"type":"boolean","default":True},"description":{"type":"string"}},"required":["metric","condition","threshold","severity"]}),
        Tool(name="delete_alert", description="Delete an alert rule by ID", inputSchema={"type":"object","properties":{"rule_id":{"type":"integer"}},"required":["rule_id"]}),

        # ── Notifications ────────────────────────────────────
        Tool(name="send_slack_alert", description="Send a Slack alert message", inputSchema={"type":"object","properties":{"message":{"type":"string"},"severity":{"type":"string","enum":["warn","critical"]},"metric":{"type":"string","default":""}},"required":["message","severity"]}),
    ]


@mcp.call_tool()
async def call_tool(name, arguments):
    logger.info(f"Tool: {name} args={arguments}")
    try:
        s = arguments.get("server_name", "local")

        # ── Core ─────────────────────────────────────────────
        if name == "ask_syswatcher":
            return _s(await _ask(arguments["question"], s))

        elif name == "run_sweep":
            r = await _api("POST", "/sweep", {"server_name": s})
            return _s(f"[{r.get('severity','healthy').upper()}]\n\n{r.get('report','')}")

        elif name == "get_server_status":
            return _t(await _api("GET", "/status", {"server_name": s, "mins_back": 5}))

        elif name == "list_servers":
            r = await _api("GET", "/servers")
            lines = [f"• {sv['name']} — {sv['ip']} (user: {sv.get('ssh_user','local')})" for sv in r.get("servers", [])]
            return _s("\n".join(lines) if lines else "No servers found")

        elif name == "get_recent_events":
            params = {"limit": arguments.get("limit", 20)}
            if "server_name" in arguments: params["server_name"] = arguments["server_name"]
            if "severity" in arguments: params["severity"] = arguments["severity"]
            r = await _api("GET", "/history/events", params)
            events = r.get("events", [])
            if not events: return _s("No events found")
            lines = [f"[{e['severity'].upper()}] {str(e['timestamp'])[:19]} {e['server_name']} — {e['message']}" for e in events]
            return _s("\n".join(lines))

        elif name == "get_sweep_history":
            params = {"limit": arguments.get("limit", 10)}
            if "server_name" in arguments: params["server_name"] = arguments["server_name"]
            r = await _api("GET", "/history/sweeps", params)
            sweeps = r.get("sweeps", [])
            if not sweeps: return _s("No sweeps found")
            lines = [f"[{sw['overall'].upper()}] {str(sw['started_at'])[:19]} {sw['server_name']}" for sw in sweeps]
            return _s("\n".join(lines))

        # ── System ───────────────────────────────────────────
        elif name == "get_cpu_stats":
            return _s(await _ask("what is the CPU usage?", s))

        elif name == "get_memory_stats":
            return _s(await _ask("what is the memory usage?", s))

        elif name == "get_disk_usage":
            return _s(await _ask(f"what is the disk usage on {arguments.get('path', '/')}?", s))

        elif name == "get_network_stats":
            return _s(await _ask("show network interface statistics", s))

        elif name == "get_top_processes":
            return _s(await _ask(f"what are the top {arguments.get('limit', 10)} processes by CPU?", s))

        elif name == "get_system_uptime":
            return _s(await _ask("what is the system uptime?", s))

        elif name == "get_load_average":
            return _s(await _ask("what is the load average?", s))

        elif name == "get_open_ports":
            return _s(await _ask("what ports are open and listening?", s))

        elif name == "get_swap_activity":
            return _s(await _ask("is the server swapping memory? show swap activity", s))

        # ── Cron ─────────────────────────────────────────────
        elif name == "get_cron_jobs":
            return _s(await _ask("list all cron jobs", s))

        elif name == "get_cron_logs":
            kw = arguments.get("filter_keyword", "")
            return _s(await _ask(f"show cron logs{' for ' + kw if kw else ''}", s))

        elif name == "get_failed_crons":
            return _s(await _ask("did any cron jobs fail?", s))

        elif name == "create_cron_job":
            q = f"create a cron job called {arguments['name']} that runs '{arguments['command']}' on schedule '{arguments['schedule']}'"
            if arguments.get("log_path"): q += f" and logs to {arguments['log_path']}"
            return _s(await _ask(q, s))

        elif name == "delete_cron_job":
            return _s(await _ask(f"delete the cron job called {arguments['name']}", s))

        # ── Process ──────────────────────────────────────────
        elif name == "get_process_by_name":
            return _s(await _ask(f"find processes named {arguments['name']}", s))

        elif name == "get_zombie_processes":
            return _s(await _ask("are there any zombie processes?", s))

        # ── Logs ─────────────────────────────────────────────
        elif name == "tail_log_file":
            return _s(await _ask(f"show last {arguments.get('lines', 50)} lines of {arguments['path']}", s))

        elif name == "search_log_pattern":
            return _s(await _ask(f"search for '{arguments['pattern']}' in {arguments['path']}", s))

        elif name == "get_auth_failures":
            return _s(await _ask("show authentication failures from auth logs", s))

        elif name == "get_error_summary":
            return _s(await _ask(f"show error summary from {arguments.get('log_path', '/var/log/syslog')}", s))

        elif name == "get_oom_events":
            return _s(await _ask("are there any OOM out of memory events?", s))

        elif name == "get_kernel_messages":
            return _s(await _ask(f"show last {arguments.get('limit', 30)} kernel messages from dmesg", s))

        elif name == "get_application_errors":
            return _s(await _ask(f"search all logs for '{arguments.get('pattern', 'error')}'", s))

        elif name == "get_log_volume_trend":
            return _s(await _ask(f"how fast is {arguments.get('log_path', '/var/log/syslog')} growing?", s))

        elif name == "get_segfault_events":
            return _s(await _ask("are there any segfault or application crash events?", s))

        # ── Prometheus ───────────────────────────────────────
        elif name == "query_prometheus_instant":
            return _s(await _ask(f"query prometheus: {arguments['promql']}", s))

        elif name == "query_prometheus_range":
            return _s(await _ask(f"query prometheus range for last {arguments.get('hours_back', 1)} hours: {arguments['promql']}", s))

        elif name == "get_prometheus_alerts":
            return _s(await _ask("are there any prometheus alerts firing?", s))

        elif name == "get_cpu_trend":
            return _s(await _ask(f"show CPU trend for last {arguments.get('hours_back', 3)} hours", s))

        elif name == "get_memory_trend":
            return _s(await _ask(f"show memory trend for last {arguments.get('hours_back', 3)} hours, is memory leaking?", s))

        elif name == "get_disk_io_rate":
            return _s(await _ask("what is the disk read write speed right now?", s))

        elif name == "get_network_bandwidth":
            return _s(await _ask("what is the network bandwidth usage right now?", s))

        elif name == "get_cpu_iowait":
            return _s(await _ask("what is the CPU iowait percentage? is disk causing slowness?", s))

        elif name == "compare_server_metrics":
            return _s(await _ask(f"compare {arguments.get('metric', 'cpu')} across all servers", "local"))

        elif name == "get_prometheus_targets":
            return _s(await _ask("check prometheus scrape targets, which servers are being monitored?", "local"))

        elif name == "get_metric_anomaly":
            return _s(await _ask(f"detect any anomalies in {arguments.get('metric', 'cpu')} metric", s))

        # ── Grafana ──────────────────────────────────────────
        elif name == "post_grafana_annotation":
            return _s(await _ask(f"post a grafana annotation: {arguments['text']} with severity {arguments.get('severity', 'warn')}", s))

        elif name == "get_grafana_annotations":
            return _s(await _ask(f"show grafana annotations from last {arguments.get('hours_back', 24)} hours", s))

        elif name == "get_annotations_timeline":
            srv = arguments.get("server_name", "")
            return _s(await _ask(f"show incident timeline for last {arguments.get('hours_back', 6)} hours{' on ' + srv if srv else ''}", s))

        elif name == "get_grafana_dashboard_list":
            return _s(await _ask("list all grafana dashboards", s))

        elif name == "get_grafana_health":
            return _s(await _ask("is grafana healthy?", s))

        # ── RCA ──────────────────────────────────────────────
        elif name == "get_rca_report":
            return _s(await _ask(f"run a full RCA root cause analysis for last {arguments.get('hours_back', 2)} hours", s))

        elif name == "get_system_baseline":
            return _s(await _ask("compare current metrics against 24 hour baseline, any deviations?", s))

        # ── Security ─────────────────────────────────────────
        elif name == "get_failed_ssh_attempts":
            return _s(await _ask(f"show last {arguments.get('limit', 20)} failed SSH login attempts", s))

        elif name == "get_active_sessions":
            return _s(await _ask("who is currently logged in? show active sessions", s))

        elif name == "get_sudo_history":
            return _s(await _ask(f"show last {arguments.get('limit', 20)} sudo commands used", s))

        elif name == "get_firewall_rules":
            return _s(await _ask("show firewall rules UFW and iptables", s))

        elif name == "get_ssl_cert_expiry":
            domains = arguments.get("domains", [])
            return _s(await _ask(f"check SSL cert expiry{' for ' + ', '.join(domains) if domains else ''}", s))

        elif name == "get_listening_services":
            return _s(await _ask("what services are listening on network ports?", s))

        elif name == "get_recent_logins":
            return _s(await _ask(f"show last {arguments.get('limit', 10)} successful logins", s))

        elif name == "get_world_writable_files":
            return _s(await _ask("find world writable files and directories", s))

        elif name == "get_failed_services":
            return _s(await _ask("are there any failed systemd services?", s))

        elif name == "get_service_status":
            return _s(await _ask(f"check if {arguments['service']} service is running", s))

        # ── Application ──────────────────────────────────────
        elif name == "check_port_open":
            host = arguments.get("host", "localhost")
            return _s(await _ask(f"is port {arguments['port']} open on {host}?", s))

        elif name == "check_url_health":
            return _s(await _ask(f"check if URL is healthy: {arguments['url']}", s))

        elif name == "check_process_alive":
            return _s(await _ask(f"is process {arguments['process_name']} running?", s))

        elif name == "get_docker_containers":
            return _s(await _ask("list all docker containers and their status", s))

        elif name == "get_docker_stats":
            return _s(await _ask("show docker container CPU and memory usage", s))

        elif name == "get_service_logs":
            return _s(await _ask(f"show last {arguments.get('lines', 50)} log lines for {arguments['service']} service", s))

        elif name == "get_environment_check":
            return _s(await _ask("check system configuration and limits", s))

        elif name == "check_disk_smart":
            return _s(await _ask("check disk health using SMART data", s))

        # ── Alerts ───────────────────────────────────────────
        elif name == "get_alert_rules":
            params = {}
            if "server_name" in arguments: params["server_name"] = arguments["server_name"]
            r = await _api("GET", "/alerts", params)
            rules = r.get("rules", [])
            if not rules: return _s("No alert rules configured")
            lines = [f"ID {rl['id']}: {rl['metric']} {rl['condition']} {rl['threshold']} → {rl['severity']} (slack={rl['notify_slack']})" for rl in rules]
            return _s("\n".join(lines))

        elif name == "create_alert":
            r = await _api("POST", "/alerts", {
                "metric": arguments["metric"], "condition": arguments["condition"],
                "threshold": arguments["threshold"], "severity": arguments["severity"],
                "notify_slack": arguments.get("notify_slack", True),
                "description": arguments.get("description", ""),
            })
            return _t(r)

        elif name == "delete_alert":
            r = await _api("DELETE", f"/alerts/{arguments['rule_id']}")
            return _t(r)

        # ── Notifications ────────────────────────────────────
        elif name == "send_slack_alert":
            return _s(await _ask(f"send a slack alert: {arguments['message']} severity {arguments['severity']}", "local"))

        else:
            return _s(f"Unknown tool: {name}")

    except Exception as e:
        logger.error(f"Tool error: {e}", exc_info=True)
        return _s(f"Error: {e}")


sse = SseServerTransport("/messages/")


async def health(request):
    return JSONResponse({"status": "ok", "service": "syswatcher-mcp", "tools": 66})


async def handle_sse(request):
    key = request.headers.get("x-api-key", "")
    if API_KEY and key != API_KEY:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp.run(streams[0], streams[1], mcp.create_initialization_options())


async def handle_messages(request):
    key = request.headers.get("x-api-key", "")
    if API_KEY and key != API_KEY:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    await sse.handle_post_message(request.scope, request.receive, request._send)


app = Starlette(routes=[
    Route("/health", health),
    Route("/sse", handle_sse),
    Mount("/messages/", routes=[Route("/{path:path}", handle_messages, methods=["POST"])]),
])

if __name__ == "__main__":
    logger.info("SysWatcher MCP Server starting on port 8080 — 66 tools")
    logger.info(f"API: {API_URL}")
    uvicorn.run(app, host="0.0.0.0", port=8080)