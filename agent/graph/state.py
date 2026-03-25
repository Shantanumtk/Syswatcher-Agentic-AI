from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # Input
    question:    str
    mode:        str          # "chat" | "sweep"
    server_name: str          # which server to query

    # Set by classifier
    intents: list[str]

    # Conversation messages (append-only via add_messages)
    messages: Annotated[list, add_messages]

    # Output
    response:      str
    severity:      str        # healthy | warn | critical
    events_stored: int
    sweep_id:      int
