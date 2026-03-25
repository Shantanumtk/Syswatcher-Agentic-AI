import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from agent.db import queries

logger = logging.getLogger("syswatcher.api.crons")
router = APIRouter()

class CreateCronRequest(BaseModel):
    server_name: str
    name:        str
    schedule:    str
    command:     str
    log_path:    str = ""

@router.get("")
async def list_crons(
    server_name: str = Query(..., description="Server name e.g. local"),
):
    try:
        crons = await queries.get_crons(server_name=server_name)
        return {"crons": crons, "count": len(crons)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
async def create_cron(req: CreateCronRequest):
    # Validate 5-part cron expression
    if len(req.schedule.split()) != 5:
        raise HTTPException(
            status_code=400,
            detail=(
                "schedule must be a 5-part cron expression "
                "e.g. '0 2 * * *' (daily at 2am)"
            ),
        )
    try:
        cron_id = await queries.insert_cron(
            server_name=req.server_name,
            name=req.name,
            schedule=req.schedule,
            command=req.command,
            log_path=req.log_path or None,
            added_by="api",
        )
        return {
            "success": True,
            "cron_id": cron_id,
            "message": (
                f"Cron '{req.name}' registered for monitoring "
                f"on {req.server_name} — schedule: {req.schedule}"
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{server_name}/{name}")
async def delete_cron(server_name: str, name: str):
    try:
        success = await queries.delete_cron(
            server_name=server_name,
            name=name,
        )
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Cron '{name}' not found on {server_name}",
            )
        return {"success": True, "message": f"Cron '{name}' removed"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{server_name}/{name}/status")
async def update_cron_status(
    server_name: str,
    name:        str,
    exit_code:   int = 0,
    status:      str = "ok",
):
    try:
        await queries.update_cron_status(
            server_name=server_name,
            name=name,
            exit_code=exit_code,
            status=status,
        )
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
