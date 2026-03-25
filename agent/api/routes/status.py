import logging
from fastapi import APIRouter, HTTPException
from db import queries
from db.postgres import get_pool

logger = logging.getLogger("syswatcher.api.status")
router = APIRouter()

@router.get("")
async def status(server_name: str = None, hours_back: int = 6):
    """
    Returns overall system health status.
    Used by the UI status bar — polls every 30s.
    """
    try:
        # DB connectivity check
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

        # Event summary
        summary = await queries.get_event_summary(
            server_name=server_name,
            hours_back=hours_back,
        )

        # Last sweep
        sweeps = await queries.get_recent_sweeps(
            server_name=server_name,
            limit=1,
        )
        last_sweep = sweeps[0] if sweeps else None

        # All servers
        servers = await queries.get_servers()

        return {
            "overall":        summary.get("overall", "healthy"),
            "critical_count": summary.get("critical", 0),
            "warn_count":     summary.get("warn", 0),
            "info_count":     summary.get("info", 0),
            "total_events":   summary.get("total", 0),
            "period_hours":   hours_back,
            "last_sweep_at":  str(last_sweep["started_at"]) if last_sweep else None,
            "last_sweep_status": last_sweep["overall"] if last_sweep else None,
            "servers":        [s["name"] for s in servers],
            "database":       "ok",
        }
    except Exception as e:
        logger.error(f"/status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
