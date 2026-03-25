import asyncio
import logging
from langchain_core.messages import HumanMessage, SystemMessage
from tools.registry import get_tools_for_intent, get_all_tools
from db import queries

logger = logging.getLogger("syswatcher.collect")

SYSTEM_PROMPT = """You are SysWatcher, an AI server health monitoring agent.

Your job:
1. Use the available tools to collect data about the server
2. Answer the user's question accurately using that data
3. For sweeps: collect ALL metrics, store events, post Grafana annotations
4. For chat: collect only what is needed to answer the question

Rules:
- Always call tools to get LIVE data — never guess metric values
- Store warn/critical findings using the event storage functions
- Only notify (Slack/email) for CRITICAL severity
- For cron setup requests: use create_cron_job tool directly — no confirmation needed
- For alert rule requests: use create_alert_rule tool directly
- Be concise in your final answer — bullet points for multiple findings
- If everything is healthy, say so clearly
"""

async def _start_sweep(server_name: str) -> int:
    try:
        return await queries.start_sweep(server_name)
    except Exception:
        return None

def collect_node(state: dict) -> dict:
    server_name = state.get("server_name", "local")
    mode        = state.get("mode", "chat")
    question    = state.get("question", "")
    intents     = state.get("intents", ["system"])

    # Start sweep record if in sweep mode
    sweep_id = None
    if mode == "sweep":
        try:
            loop = asyncio.new_event_loop()
            sweep_id = loop.run_until_complete(_start_sweep(server_name))
            loop.close()
        except Exception as e:
            logger.warning(f"Could not start sweep record: {e}")

    # Build messages for the agent
    system_msg = SystemMessage(content=SYSTEM_PROMPT)

    if mode == "sweep":
        human_content = (
            f"Run a full health sweep on server '{server_name}'. "
            f"Check CPU, memory, disk (all mounts), network, load average, "
            f"open ports, cron jobs, recent cron logs, and any Prometheus alerts. "
            f"Store all findings as events. Post a Grafana annotation with the summary. "
            f"Return a concise health report."
        )
    else:
        human_content = (
            f"Server: {server_name}\n"
            f"Question: {question}"
        )

    human_msg = HumanMessage(content=human_content)

    existing = state.get("messages", [])
    if not existing:
        messages = [system_msg, human_msg]
    else:
        messages = existing + [human_msg]

    return {
        "messages":  messages,
        "sweep_id":  sweep_id,
    }
