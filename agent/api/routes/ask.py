import uuid
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from graph import syswatcher_graph
from db import queries

logger = logging.getLogger("syswatcher.api.ask")
router = APIRouter()

class AskRequest(BaseModel):
    question:    str
    thread_id:   str = ""
    server_name: str = "local"

class AskResponse(BaseModel):
    answer:    str
    severity:  str
    thread_id: str
    server:    str

@router.post("", response_model=AskResponse)
async def ask(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question cannot be empty")

    thread_id = req.thread_id or str(uuid.uuid4())
    config    = {"configurable": {"thread_id": thread_id}}

    try:
        await queries.upsert_chat_session(thread_id, req.server_name)

        result = syswatcher_graph.invoke(
            {
                "question":      req.question,
                "mode":          "chat",
                "server_name":   req.server_name,
                "intents":       [],
                "messages":      [],
                "response":      "",
                "severity":      "healthy",
                "events_stored": 0,
                "sweep_id":      None,
            },
            config=config,
        )
        return AskResponse(
            answer=result.get("response", ""),
            severity=result.get("severity", "healthy"),
            thread_id=thread_id,
            server=req.server_name,
        )
    except Exception as e:
        logger.error(f"/ask error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
