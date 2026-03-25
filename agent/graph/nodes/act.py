import json
import logging
from langchain_core.messages import ToolMessage
from agent.tools.registry import get_all_tools

logger = logging.getLogger("syswatcher.act")

# Build lookup: tool name -> callable
_TOOL_MAP = {t.name: t for t in get_all_tools()}

def act_node(state: dict) -> dict:
    """Execute all tool calls requested by the LLM."""
    messages = state.get("messages", [])
    last_msg = messages[-1]

    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return {}

    tool_messages = []
    for call in last_msg.tool_calls:
        tool_name = call["name"]
        tool_args = call["args"]
        call_id   = call["id"]

        logger.info(f"Executing tool: {tool_name}({tool_args})")

        tool_fn = _TOOL_MAP.get(tool_name)
        if not tool_fn:
            result = {"error": f"Tool '{tool_name}' not found"}
        else:
            try:
                result = tool_fn.invoke(tool_args)
            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                result = {"error": str(e)}

        # Serialize result to string for ToolMessage
        if isinstance(result, (dict, list)):
            content = json.dumps(result, default=str)
        else:
            content = str(result)

        tool_messages.append(
            ToolMessage(content=content, tool_call_id=call_id)
        )
        logger.info(f"Tool {tool_name} completed")

    return {"messages": tool_messages}
