import asyncio
import logging
import os
import requests
from langchain_openai import ChatOpenAI
from config import settings
from db import queries

logger = logging.getLogger("syswatcher.report")

async def _finish(sweep_id, overall, summary, event_count, duration_ms):
    try:
        await queries.finish_sweep(sweep_id, overall, summary, event_count, duration_ms)
    except Exception as e:
        logger.warning(f"Could not finish sweep record: {e}")

async def _evaluate_and_notify(server_name: str, metrics: dict):
    """Evaluate alert rules against collected metrics and send Slack if breached."""
    if not metrics:
        logger.info("No metrics to evaluate")
        return

    logger.info(f"Evaluating alert rules against metrics: {metrics}")

    try:
        rules = await queries.get_alert_rules(server_name=server_name)
    except Exception as e:
        logger.warning(f"Could not fetch alert rules: {e}")
        return

    slack_webhook = os.getenv("SLACK_WEBHOOK_URL", "")
    triggered_count = 0

    for rule in rules:
        metric    = rule["metric"]
        condition = rule["condition"]
        threshold = float(rule["threshold"])
        severity  = rule["severity"]

        if metric not in metrics:
            continue

        value = float(metrics[metric])
        triggered = (
            (condition == "gt" and value > threshold) or
            (condition == "lt" and value < threshold) or
            (condition == "eq" and value == threshold)
        )

        if not triggered:
            continue

        triggered_count += 1
        logger.info(f"ALERT TRIGGERED: {metric}={value:.1f} {condition} {threshold} severity={severity}")

        # Store event in DB
        try:
            await queries.insert_event(
                server_name=server_name,
                severity=severity,
                category="system",
                metric=metric,
                value=value,
                message=f"Alert: {metric} is {value:.1f} (threshold: {condition} {threshold})",
            )
        except Exception as e:
            logger.warning(f"Could not store alert event: {e}")

        # Send Slack notification
        if rule.get("notify_slack") and slack_webhook:
            emoji = ":rotating_light:" if severity == "critical" else ":warning:"
            color = "#e53935" if severity == "critical" else "#ff9800"
            payload = {
                "attachments": [{
                    "color": color,
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"{emoji} *SysWatcher {severity.upper()} Alert*\n"
                                    f"*Server:* `{server_name}`\n"
                                    f"*Metric:* `{metric}`\n"
                                    f"*Value:* `{value:.1f}`\n"
                                    f"*Threshold:* `{condition} {threshold}`\n"
                                    f"*Description:* {rule.get('description', '')}"
                                )
                            }
                        }
                    ]
                }]
            }
            try:
                r = requests.post(slack_webhook, json=payload, timeout=5)
                if r.status_code == 200:
                    logger.info(f"Slack alert sent: {metric}={value:.1f}")
                else:
                    logger.warning(f"Slack returned {r.status_code}: {r.text}")
            except Exception as e:
                logger.error(f"Slack send failed: {e}")

    logger.info(f"Alert evaluation complete — {triggered_count} rule(s) triggered")

def report_node(state: dict) -> dict:
    messages         = state.get("messages", [])
    mode             = state.get("mode", "chat")
    sweep_id         = state.get("sweep_id")
    server_name      = state.get("server_name", "local")
    collected_metrics = state.get("collected_metrics", {})

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )

    final = llm.invoke(messages)
    response_text = final.content

    resp_lower = response_text.lower()
    if any(w in resp_lower for w in ["critical", "urgent", "immediate", "danger"]):
        severity = "critical"
    elif any(w in resp_lower for w in ["warning", "warn", "elevated", "attention", "high"]):
        severity = "warn"
    else:
        severity = "healthy"

    # Evaluate alert rules and send Slack if in sweep mode
    if mode == "sweep" and collected_metrics:
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_evaluate_and_notify(server_name, collected_metrics))
            loop.close()
        except Exception as e:
            logger.warning(f"Alert evaluation failed: {e}")

    # Finalise sweep record
    if mode == "sweep" and sweep_id:
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_finish(
                sweep_id=sweep_id,
                overall=severity,
                summary=response_text[:500],
                event_count=state.get("events_stored", 0),
                duration_ms=0,
            ))
            loop.close()
        except Exception as e:
            logger.warning(f"Sweep finalize failed: {e}")

    logger.info(f"Report complete — severity={severity} metrics={list(collected_metrics.keys())}")

    return {
        "response":          response_text,
        "severity":          severity,
        "messages":          [final],
        "collected_metrics": collected_metrics,
    }
