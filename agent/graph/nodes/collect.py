import asyncio
import logging
from langchain_core.messages import HumanMessage, SystemMessage
from db import queries

logger = logging.getLogger("syswatcher.collect")

SYSTEM_PROMPT = """You are SysWatcher, an AI server health monitoring agent.

Your job:
1. Use the available tools to collect data about the server
2. Answer the user question accurately using that data
3. For sweeps: collect ALL metrics, store events, post Grafana annotations
4. For chat: collect only what is needed to answer the question

CRITICAL RULES:
- ALWAYS pass server_name parameter to tools when the server is not local
- If server_name is "dev", "test" or any non-local server, pass server_name to ALL tool calls
- Never guess metric values — always call tools to get LIVE data
- Store warn/critical findings as events
- Only notify (Slack/email) for CRITICAL severity
- For cron setup requests: use create_cron_job tool directly
- For alert rule requests: use create_alert_rule tool directly
- Be concise in final answer — bullet points for multiple findings
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

    sweep_id = None
    if mode == "sweep":
        try:
            loop = asyncio.new_event_loop()
            sweep_id = loop.run_until_complete(_start_sweep(server_name))
            loop.close()
        except Exception as e:
            logger.warning(f"Could not start sweep record: {e}")

    system_msg = SystemMessage(content=SYSTEM_PROMPT)

    if mode == "sweep":
        human_content = (
            f"Run a full health sweep on server \'{server_name}\'. "
            f"IMPORTANT: Pass server_name=\'{server_name}\' to every tool call. "
            f"Check CPU, memory, disk, network, load average, open ports, "
            f"cron jobs, recent cron logs, and Prometheus alerts. "
            f"Store all findings as events. Post a Grafana annotation. "
            f"Return a concise health report."
        )
    else:
        human_content = (
            f"Server: {server_name}\n"
            f"IMPORTANT: Pass server_name=\'{server_name}\' to every tool call.\n"
            f"Question: {question}"
        )

    human_msg = HumanMessage(content=human_content)
    existing = state.get("messages", [])
    messages = [system_msg, human_msg] if not existing else existing + [human_msg]

    return {"messages": messages, "sweep_id": sweep_id}
