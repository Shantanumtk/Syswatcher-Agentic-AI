import asyncio
from langchain_core.tools import tool
from agent.db import queries

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
def list_monitored_servers() -> list:
    """List all servers SysWatcher is monitoring.
    Use when asked: 'what servers are monitored?', 'show servers', 'list servers'
    """
    try:
        servers = _run(queries.get_servers())
        return servers if servers else [{"info": "No servers registered"}]
    except Exception as e:
        return [{"error": str(e)}]

@tool
def get_server_summary(server_name: str, hours_back: int = 6) -> dict:
    """Get health summary for a specific server over a time period.
    Use when asked: 'how is prod-01?', 'status of staging server', 'server summary'
    server_name: name of server e.g. 'prod-01', 'local'
    hours_back:  hours of history (default 6)
    """
    try:
        summary = _run(queries.get_event_summary(
            server_name=server_name, hours_back=hours_back
        ))
        sweeps = _run(queries.get_recent_sweeps(server_name=server_name, limit=1))
        last_sweep = sweeps[0] if sweeps else None
        return {
            "server_name":  server_name,
            "period_hours": hours_back,
            "overall":      summary.get("overall", "unknown"),
            "critical":     summary.get("critical", 0),
            "warn":         summary.get("warn", 0),
            "info":         summary.get("info", 0),
            "total_events": summary.get("total", 0),
            "last_sweep":   str(last_sweep.get("started_at")) if last_sweep else "never",
            "last_sweep_status": last_sweep.get("overall") if last_sweep else None,
        }
    except Exception as e:
        return {"error": str(e)}
