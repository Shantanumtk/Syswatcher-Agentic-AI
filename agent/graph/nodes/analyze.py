import logging
from langchain_openai import ChatOpenAI
from config import settings
from tools.registry import get_tools_for_intent, get_all_tools

logger = logging.getLogger("syswatcher.analyze")

def analyze_node(state: dict) -> dict:
    mode    = state.get("mode", "chat")
    intents = state.get("intents", ["system"])

    # Pick tools based on intent
    if mode == "sweep":
        tools = get_all_tools()
    else:
        tools = get_tools_for_intent(intents)

    logger.info(f"Analyze node — mode={mode} intents={intents} tools={len(tools)}")

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=0,
    ).bind_tools(tools)

    messages  = state.get("messages", [])
    response  = llm.invoke(messages)

    logger.info(
        f"LLM response — tool_calls={len(response.tool_calls) if hasattr(response,'tool_calls') else 0}"
    )

    return {"messages": [response]}
