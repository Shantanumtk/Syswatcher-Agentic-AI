import json
import logging
from langchain_core.messages import ToolMessage
from tools.registry import get_all_tools

logger = logging.getLogger("syswatcher.act")
_TOOL_MAP = {t.name: t for t in get_all_tools()}

METRIC_TOOLS = {
    "get_cpu_stats":    lambda r: {"cpu_usage_pct": r.get("cpu_percent", 0)},
    "get_memory_stats": lambda r: {"memory_usage_pct": r.get("percent", 0)},
    "get_disk_usage":   lambda r: {"disk_usage_pct": r.get("percent", 0)},
    "get_load_average": lambda r: {"load_avg_1m": r.get("load_1m", 0)},
}

def act_node(state: dict) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1]

    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return {}

    tool_messages = []
    collected_metrics = state.get("collected_metrics", {})

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

        # Extract metrics for alert evaluation
        if tool_name in METRIC_TOOLS and isinstance(result, dict) and "error" not in result:
            try:
                metrics = METRIC_TOOLS[tool_name](result)
                collected_metrics.update(metrics)
                logger.info(f"Extracted metrics: {metrics}")
            except Exception as e:
                logger.warning(f"Could not extract metrics from {tool_name}: {e}")

        content = json.dumps(result, default=str) if isinstance(result, (dict, list)) else str(result)
        tool_messages.append(ToolMessage(content=content, tool_call_id=call_id))
        logger.info(f"Tool {tool_name} completed")

    return {"messages": tool_messages, "collected_metrics": collected_metrics}
