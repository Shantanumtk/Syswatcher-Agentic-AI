import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db import queries

logger = logging.getLogger("syswatcher.api.servers")
router = APIRouter()

class AddServerRequest(BaseModel):
    name:         str
    ip:           str
    ssh_user:     str = ""
    ssh_key_path: str = ""

@router.get("")
async def list_servers():
    try:
        servers = await queries.get_servers()
        return {"servers": servers, "count": len(servers)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
async def add_server(req: AddServerRequest):
    try:
        server_id = await queries.upsert_server(
            name=req.name,
            ip=req.ip,
            ssh_user=req.ssh_user,
            ssh_key_path=req.ssh_key_path,
        )
        return {
            "success": True,
            "id":      server_id,
            "message": f"Server '{req.name}' registered",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{server_name}/summary")
async def server_summary(server_name: str, hours_back: int = 6):
    try:
        summary = await queries.get_event_summary(
            server_name=server_name,
            hours_back=hours_back,
        )
        sweeps = await queries.get_recent_sweeps(
            server_name=server_name,
            limit=3,
        )
        return {
            "server_name":  server_name,
            "period_hours": hours_back,
            **summary,
            "recent_sweeps": sweeps,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
