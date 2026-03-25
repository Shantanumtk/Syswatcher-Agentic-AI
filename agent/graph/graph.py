import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from graph.state import AgentState
from graph.nodes.classifier import classifier_node
from graph.nodes.collect    import collect_node
from graph.nodes.analyze    import analyze_node
from graph.nodes.act        import act_node
from graph.nodes.report     import report_node

logger = logging.getLogger("syswatcher.graph")

def _should_continue(state: AgentState) -> str:
    """
    After analyze: if LLM requested tool calls -> go to act.
    If LLM gave final answer -> go to report.
    """
    messages = state.get("messages", [])
    if not messages:
        return "report"
    last = messages[-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "act"
    return "report"

def _after_act(state: AgentState) -> str:
    """After executing tools, always go back to analyze."""
    return "analyze"

def build_graph(use_memory: bool = True):
    graph = StateGraph(AgentState)

    # ── Nodes ────────────────────────────────────
    graph.add_node("classifier", classifier_node)
    graph.add_node("collect",    collect_node)
    graph.add_node("analyze",    analyze_node)
    graph.add_node("act",        act_node)
    graph.add_node("report",     report_node)

    # ── Edges ────────────────────────────────────
    graph.set_entry_point("classifier")
    graph.add_edge("classifier", "collect")
    graph.add_edge("collect",    "analyze")

    # After analyze: tool calls? -> act, else -> report
    graph.add_conditional_edges(
        "analyze",
        _should_continue,
        {"act": "act", "report": "report"},
    )

    # After act: always back to analyze (may need more tool calls)
    graph.add_edge("act", "analyze")

    # report is terminal
    graph.add_edge("report", END)

    # ── Compile ───────────────────────────────────
    checkpointer = MemorySaver() if use_memory else None
    compiled = graph.compile(checkpointer=checkpointer)
    logger.info("SysWatcher graph compiled")
    return compiled

# Singleton — imported by FastAPI
syswatcher_graph = build_graph(use_memory=True)
