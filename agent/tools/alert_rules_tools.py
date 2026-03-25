import asyncio
from langchain_core.tools import tool
from db import queries

def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=10)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)

@tool
def create_alert_rule(
    metric: str,
    condition: str,
    threshold: float,
    severity: str,
    server_name: str = None,
    notify_slack: bool = False,
    notify_email: bool = False,
    description: str = "",
) -> dict:
    """Create a custom alert rule that triggers during sweeps.
    Use when asked: 'alert me if disk > 80%', 'notify when CPU > 90%',
    'set alert for memory above 95%'

    metric:     what to monitor e.g. 'disk_usage_pct', 'cpu_usage_pct',
                'memory_usage_pct', 'load_avg_1m'
    condition:  'gt' (greater than), 'lt' (less than), 'eq' (equal)
    threshold:  numeric value e.g. 80.0
    severity:   'warn' (store only) | 'critical' (store + notify)
    server_name: specific server or None for all servers
    notify_slack: send Slack when triggered (critical recommended)
    notify_email: send email when triggered
    description: human-readable description
    """
    try:
        rule_id = _run(queries.insert_alert_rule(
            metric=metric,
            condition=condition,
            threshold=threshold,
            severity=severity,
            server_name=server_name,
            notify_slack=notify_slack,
            notify_email=notify_email,
            description=description,
        ))
        return {
            "success":     True,
            "rule_id":     rule_id,
            "metric":      metric,
            "condition":   condition,
            "threshold":   threshold,
            "severity":    severity,
            "server_name": server_name or "all servers",
            "message":     f"Alert rule created — will trigger when {metric} {condition} {threshold}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@tool
def list_alert_rules(server_name: str = None) -> list:
    """List all active alert rules.
    Use when asked: 'show alert rules', 'what alerts are configured?',
    'list my alerts'
    server_name: filter by server or None for all
    """
    try:
        rules = _run(queries.get_alert_rules(server_name=server_name))
        if not rules:
            return [{"info": "No alert rules configured"}]
        return [
            {
                "id":          r["id"],
                "metric":      r["metric"],
                "condition":   r["condition"],
                "threshold":   float(r["threshold"]),
                "severity":    r["severity"],
                "server":      r["server_name"] or "all",
                "notify_slack":r["notify_slack"],
                "notify_email":r["notify_email"],
                "description": r["description"],
            }
            for r in rules
        ]
    except Exception as e:
        return [{"error": str(e)}]

@tool
def remove_alert_rule(rule_id: int) -> dict:
    """Remove an alert rule by its ID.
    Use when asked: 'delete alert rule 3', 'remove the disk alert',
    'turn off CPU alert'
    rule_id: the numeric ID from list_alert_rules
    """
    try:
        success = _run(queries.delete_alert_rule(rule_id))
        if success:
            return {"success": True, "message": f"Alert rule {rule_id} removed"}
        return {"success": False, "error": f"Rule {rule_id} not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}
