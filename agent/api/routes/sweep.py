import uuid
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from graph import syswatcher_graph

logger = logging.getLogger("syswatcher.api.sweep")
router = APIRouter()

class SweepRequest(BaseModel):
    server_name: str = "local"

class SweepResponse(BaseModel):
    report:   str
    severity: str
    server:   str

@router.post("", response_model=SweepResponse)
async def sweep(req: SweepRequest = SweepRequest()):
    thread_id = f"sweep-{req.server_name}-{uuid.uuid4().hex[:8]}"
    config    = {"configurable": {"thread_id": thread_id}}

    try:
        result = syswatcher_graph.invoke(
            {
                "question":      "",
                "mode":          "sweep",
                "server_name":   req.server_name,
                "intents":       [],
                "messages":      [],
                "response":      "",
                "severity":      "healthy",
                "events_stored": 0,
                "sweep_id":      None,
                "collected_metrics": {},
            },
            config=config,
        )
        return SweepResponse(
            report=result.get("response", ""),
            severity=result.get("severity", "healthy"),
            server=req.server_name,
        )
    except Exception as e:
        logger.error(f"/sweep error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
