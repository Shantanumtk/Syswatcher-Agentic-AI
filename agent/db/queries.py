import json
import logging
from datetime import datetime, timezone
from typing import Optional
from db.postgres import get_pool

logger = logging.getLogger("syswatcher.db")

# ═══════════════════════════════════════════════
# Events
# ═══════════════════════════════════════════════

async def insert_event(
    server_name: str,
    severity: str,
    category: str,
    message: str,
    metric: str = None,
    value: float = None,
    raw: dict = None,
    sweep_id: int = None,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO events
                (server_name, sweep_id, severity, category, metric, value, message, raw)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
        """,
            server_name,
            sweep_id,
            severity,
            category,
            metric,
            value,
            message,
            json.dumps(raw) if raw else None,
        )
        return row["id"]

async def get_events(
    server_name: str = None,
    hours_back: int = 6,
    severity: str = None,
    category: str = None,
    limit: int = 100,
) -> list[dict]:
    pool = await get_pool()
    query = """
        SELECT id, server_name, timestamp, severity, category,
               metric, value, message, notified
        FROM events
        WHERE timestamp > NOW() - ($1 || ' hours')::interval
    """
    params = [str(hours_back)]
    idx = 2

    if server_name:
        query += f" AND server_name = ${idx}"; params.append(server_name); idx += 1
    if severity:
        query += f" AND severity = ${idx}"; params.append(severity); idx += 1
    if category:
        query += f" AND category = ${idx}"; params.append(category); idx += 1

    query += f" ORDER BY timestamp DESC LIMIT ${idx}"
    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]

async def get_event_summary(
    server_name: str = None,
    hours_back: int = 6,
) -> dict:
    pool = await get_pool()
    query = """
        SELECT
            severity,
            COUNT(*)::int AS count
        FROM events
        WHERE timestamp > NOW() - ($1 || ' hours')::interval
    """
    params = [str(hours_back)]

    if server_name:
        query += " AND server_name = $2"
        params.append(server_name)

    query += " GROUP BY severity"

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    summary = {"critical": 0, "warn": 0, "info": 0, "total": 0}
    for row in rows:
        summary[row["severity"]] = row["count"]
        summary["total"] += row["count"]

    if summary["critical"] > 0:
        summary["overall"] = "critical"
    elif summary["warn"] > 0:
        summary["overall"] = "warn"
    else:
        summary["overall"] = "healthy"

    return summary

async def mark_notified(event_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE events SET notified = TRUE WHERE id = $1", event_id
        )

# ═══════════════════════════════════════════════
# Sweep runs
# ═══════════════════════════════════════════════

async def start_sweep(server_name: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO sweep_runs (server_name)
            VALUES ($1) RETURNING id
        """, server_name)
        return row["id"]

async def finish_sweep(
    sweep_id: int,
    overall: str,
    summary: str,
    event_count: int,
    duration_ms: int,
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE sweep_runs
            SET finished_at  = NOW(),
                overall      = $2,
                summary      = $3,
                event_count  = $4,
                duration_ms  = $5
            WHERE id = $1
        """, sweep_id, overall, summary, event_count, duration_ms)

async def get_recent_sweeps(
    server_name: str = None,
    limit: int = 10
) -> list[dict]:
    pool = await get_pool()
    query = """
        SELECT id, server_name, started_at, finished_at,
               duration_ms, overall, summary, event_count
        FROM sweep_runs
    """
    params = []
    if server_name:
        query += " WHERE server_name = $1"
        params.append(server_name)
    query += " ORDER BY started_at DESC LIMIT " + str(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]

# ═══════════════════════════════════════════════
# Alert rules
# ═══════════════════════════════════════════════

async def insert_alert_rule(
    metric: str,
    condition: str,
    threshold: float,
    severity: str,
    server_name: str = None,
    notify_slack: bool = False,
    notify_email: bool = False,
    description: str = "",
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO alert_rules
                (server_name, metric, condition, threshold, severity,
                 notify_slack, notify_email, description)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            RETURNING id
        """,
            server_name, metric, condition, threshold,
            severity, notify_slack, notify_email, description,
        )
        return row["id"]

async def get_alert_rules(
    server_name: str = None,
    active_only: bool = True,
) -> list[dict]:
    pool = await get_pool()
    query = "SELECT * FROM alert_rules WHERE 1=1"
    params = []
    idx = 1

    if active_only:
        query += " AND active = TRUE"
    if server_name:
        query += f" AND (server_name = ${idx} OR server_name IS NULL)"
        params.append(server_name); idx += 1

    query += " ORDER BY created_at DESC"

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]

async def delete_alert_rule(rule_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE alert_rules SET active = FALSE WHERE id = $1", rule_id
        )
        return result == "UPDATE 1"

async def evaluate_alert_rules(
    server_name: str,
    metric: str,
    value: float,
) -> list[dict]:
    """Return any rules triggered by this metric value."""
    rules = await get_alert_rules(server_name=server_name)
    triggered = []
    for rule in rules:
        if rule["metric"] != metric:
            continue
        cond = rule["condition"]
        thr  = float(rule["threshold"])
        if   cond == "gt" and value >  thr: triggered.append(rule)
        elif cond == "lt" and value <  thr: triggered.append(rule)
        elif cond == "eq" and value == thr: triggered.append(rule)
    return triggered

# ═══════════════════════════════════════════════
# Cron registry
# ═══════════════════════════════════════════════

async def insert_cron(
    server_name: str,
    name: str,
    schedule: str,
    command: str,
    log_path: str = None,
    added_by: str = "user",
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO cron_registry
                (server_name, name, schedule, command, log_path, added_by)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (server_name, name)
            DO UPDATE SET schedule=$3, command=$4, log_path=$5, active=TRUE
            RETURNING id
        """, server_name, name, schedule, command, log_path, added_by)
        return row["id"]

async def update_cron_status(
    server_name: str,
    name: str,
    exit_code: int,
    status: str,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE cron_registry
            SET last_run_at    = NOW(),
                last_exit_code = $3,
                last_status    = $4,
                fail_count     = CASE WHEN $4 = 'failed'
                                 THEN fail_count + 1 ELSE 0 END
            WHERE server_name = $1 AND name = $2
        """, server_name, name, exit_code, status)

async def get_crons(
    server_name: str,
    active_only: bool = True,
) -> list[dict]:
    pool = await get_pool()
    query = "SELECT * FROM cron_registry WHERE server_name = $1"
    if active_only:
        query += " AND active = TRUE"
    query += " ORDER BY name"
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, server_name)
    return [dict(r) for r in rows]

async def delete_cron(server_name: str, name: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE cron_registry SET active = FALSE
            WHERE server_name = $1 AND name = $2
        """, server_name, name)
        return result == "UPDATE 1"

# ═══════════════════════════════════════════════
# Servers
# ═══════════════════════════════════════════════

async def upsert_server(
    name: str,
    ip: str,
    ssh_user: str = None,
    ssh_key_path: str = None,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO servers (name, ip, ssh_user, ssh_key_path)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (name)
            DO UPDATE SET ip=$2, ssh_user=$3, ssh_key_path=$4, active=TRUE
            RETURNING id
        """, name, ip, ssh_user, ssh_key_path)
        return row["id"]

async def get_servers(active_only: bool = True) -> list[dict]:
    pool = await get_pool()
    query = "SELECT * FROM servers"
    if active_only:
        query += " WHERE active = TRUE"
    query += " ORDER BY name"
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
    return [dict(r) for r in rows]

# ═══════════════════════════════════════════════
# Notifications log
# ═══════════════════════════════════════════════

async def log_notification(
    channel: str,
    severity: str,
    message: str,
    server_name: str = None,
    event_id: int = None,
    success: bool = True,
    error: str = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO notifications
                (server_name, event_id, channel, severity, message, success, error)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
        """, server_name, event_id, channel, severity, message, success, error)

# ═══════════════════════════════════════════════
# Chat sessions
# ═══════════════════════════════════════════════

async def upsert_chat_session(
    thread_id: str,
    server_name: str = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO chat_sessions (thread_id, server_name)
            VALUES ($1, $2)
            ON CONFLICT (thread_id)
            DO UPDATE SET last_active = NOW(),
                          message_count = chat_sessions.message_count + 1
        """, thread_id, server_name)
