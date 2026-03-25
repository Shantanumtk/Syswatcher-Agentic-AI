import asyncio
import logging
from langchain_openai import ChatOpenAI
from config import settings
from db import queries

logger = logging.getLogger("syswatcher.report")

async def _finish(sweep_id, overall, summary, event_count, duration_ms):
    try:
        await queries.finish_sweep(sweep_id, overall, summary, event_count, duration_ms)
    except Exception as e:
        logger.warning(f"Could not finish sweep record: {e}")

def report_node(state: dict) -> dict:
    """
    Final node — LLM has all tool results in messages.
    Generate the human-readable response.
    For sweeps: also finalise the sweep_run record.
    """
    messages = state.get("messages", [])
    mode     = state.get("mode", "chat")
    sweep_id = state.get("sweep_id")

    # One final LLM call with all tool results in context
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )

    final = llm.invoke(messages)
    response_text = final.content

    # Determine overall severity from response text
    resp_lower = response_text.lower()
    if any(w in resp_lower for w in ["critical", "urgent", "immediate", "danger"]):
        severity = "critical"
    elif any(w in resp_lower for w in ["warning", "warn", "elevated", "attention", "high"]):
        severity = "warn"
    else:
        severity = "healthy"

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

    logger.info(f"Report complete — severity={severity}")

    return {
        "response": response_text,
        "severity": severity,
        "messages": [final],
    }
