from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    question:          str
    mode:              str
    server_name:       str
    intents:           list[str]
    messages:          Annotated[list, add_messages]
    response:          str
    severity:          str
    events_stored:     int
    sweep_id:          int
    collected_metrics: dict
