import logging
import os
import asyncio
import concurrent.futures
import requests
import psycopg2
import psycopg2.extras
from langchain_openai import ChatOpenAI
from config import settings

logger = logging.getLogger("syswatcher.report")

def _get_pg_conn():
    """Create a fresh sync postgres connection."""
    return psycopg2.connect(os.getenv("DATABASE_URL", ""))

def _evaluate_and_notify_sync(server_name: str, metrics: dict):
    """Evaluate alert rules using sync psycopg2 — no event loop needed."""
    if not metrics:
        logger.info("No metrics to evaluate")
        return

    logger.info(f"Evaluating alert rules against metrics: {metrics}")

    try:
        conn = _get_pg_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Fetch alert rules
        cur.execute("""
            SELECT * FROM alert_rules
            WHERE active = TRUE
            AND (server_name = %s OR server_name IS NULL)
            ORDER BY created_at DESC
        """, (server_name,))
        rules = cur.fetchall()
    except Exception as e:
        logger.warning(f"Could not fetch alert rules: {e}")
        return

    slack_webhook    = os.getenv("SLACK_WEBHOOK_URL", "")
    triggered_count  = 0

    for rule in rules:
        metric    = rule["metric"]
        condition = rule["condition"]
        threshold = float(rule["threshold"])
        severity  = rule["severity"]

        if metric not in metrics:
            continue

        value     = float(metrics[metric])
        triggered = (
            (condition == "gt" and value > threshold) or
            (condition == "lt" and value < threshold) or
            (condition == "eq" and value == threshold)
        )

        if not triggered:
            continue

        triggered_count += 1
        logger.info(f"ALERT TRIGGERED: {metric}={value:.1f} {condition} {threshold} severity={severity}")

        # Store event
        try:
            cur.execute("""
                INSERT INTO events (server_name, severity, category, metric, value, message)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                server_name, severity, "system", metric, value,
                f"Alert: {metric} is {value:.1f} (threshold: {condition} {threshold})"
            ))
            conn.commit()
        except Exception as e:
            logger.warning(f"Could not store alert event: {e}")
            conn.rollback()

        # Send Slack
        if rule.get("notify_slack") and slack_webhook:
            emoji = ":rotating_light:" if severity == "critical" else ":warning:"
            color = "#e53935" if severity == "critical" else "#ff9800"
            payload = {
                "attachments": [{
                    "color": color,
                    "blocks": [{
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
                    }]
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

    cur.close()
    conn.close()
    logger.info(f"Alert evaluation complete — {triggered_count} rule(s) triggered")

def _finish_sweep_sync(sweep_id, overall, summary, event_count, duration_ms):
    """Finalize sweep record using sync psycopg2."""
    try:
        conn = _get_pg_conn()
        cur  = conn.cursor()
        cur.execute("""
            UPDATE sweep_runs
            SET finished_at = NOW(), overall = %s, summary = %s,
                event_count = %s, duration_ms = %s
            WHERE id = %s
        """, (overall, summary, event_count, duration_ms, sweep_id))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not finish sweep record: {e}")

def report_node(state: dict) -> dict:
    messages          = state.get("messages", [])
    mode              = state.get("mode", "chat")
    sweep_id          = state.get("sweep_id")
    server_name       = state.get("server_name", "local")
    collected_metrics = state.get("collected_metrics", {})

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )

    final         = llm.invoke(messages)
    response_text = final.content

    resp_lower = response_text.lower()
    if any(w in resp_lower for w in ["critical", "urgent", "immediate", "danger"]):
        severity = "critical"
    elif any(w in resp_lower for w in ["warning", "warn", "elevated", "attention", "high"]):
        severity = "warn"
    else:
        severity = "healthy"

    # Evaluate alert rules using sync DB in thread pool
    if mode == "sweep" and collected_metrics:
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    _evaluate_and_notify_sync, server_name, collected_metrics
                )
                future.result(timeout=15)
        except concurrent.futures.TimeoutError:
            logger.warning("Alert evaluation timed out after 15s")
        except Exception as e:
            logger.warning(f"Alert evaluation failed: {e}")

    # Finalize sweep record
    if mode == "sweep" and sweep_id:
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    _finish_sweep_sync, sweep_id, severity,
                    response_text[:500], state.get("events_stored", 0), 0
                )
                future.result(timeout=10)
        except Exception as e:
            logger.warning(f"Sweep finalize failed: {e}")

    logger.info(f"Report complete — severity={severity} metrics={list(collected_metrics.keys())}")

    return {
        "response":          response_text,
        "severity":          severity,
        "messages":          [final],
        "collected_metrics": collected_metrics,
    }
