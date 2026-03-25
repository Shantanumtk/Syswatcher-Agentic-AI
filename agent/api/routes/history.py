import logging
from fastapi import APIRouter, HTTPException, Query
from agent.db import queries

logger = logging.getLogger("syswatcher.api.history")
router = APIRouter()

@router.get("/events")
async def get_events(
    server_name: str  = Query(None,  description="Filter by server name"),
    hours_back:  int  = Query(24,    description="Hours of history"),
    severity:    str  = Query(None,  description="Filter: info | warn | critical"),
    category:    str  = Query(None,  description="Filter: system | cron | logs | prometheus"),
    limit:       int  = Query(100,   description="Max results", le=500),
):
    try:
        events = await queries.get_events(
            server_name=server_name,
            hours_back=hours_back,
            severity=severity,
            category=category,
            limit=limit,
        )
        return {"events": events, "count": len(events)}
    except Exception as e:
        logger.error(f"/history/events error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sweeps")
async def get_sweeps(
    server_name: str = Query(None, description="Filter by server name"),
    limit:       int = Query(10,   description="Max results", le=100),
):
    try:
        sweeps = await queries.get_recent_sweeps(
            server_name=server_name,
            limit=limit,
        )
        return {"sweeps": sweeps, "count": len(sweeps)}
    except Exception as e:
        logger.error(f"/history/sweeps error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/summary")
async def get_summary(
    server_name: str = Query(None, description="Filter by server"),
    hours_back:  int = Query(24,   description="Hours of history"),
):
    try:
        summary = await queries.get_event_summary(
            server_name=server_name,
            hours_back=hours_back,
        )
        events = await queries.get_events(
            server_name=server_name,
            hours_back=hours_back,
            severity="critical",
            limit=5,
        )
        warns = await queries.get_events(
            server_name=server_name,
            hours_back=hours_back,
            severity="warn",
            limit=5,
        )
        return {
            **summary,
            "top_critical": events,
            "top_warns":    warns,
        }
    except Exception as e:
        logger.error(f"/history/summary error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
