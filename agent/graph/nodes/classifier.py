import logging
from graph.state import AgentState
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from config import settings

logger = logging.getLogger("syswatcher.classifier")

_llm = ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key, temperature=0)

_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an intent classifier for a server health agent.
Return a JSON list of relevant tool groups only, no markdown.

Groups: system, cron, process, logs, prometheus, grafana, alerts, notification

Examples:
  "is everything ok" -> ["system","cron","prometheus","logs"]
  "CPU usage" -> ["system","prometheus"]
  "cron jobs" -> ["cron","logs"]
  "alert rules" -> ["alerts"]
  "disk usage" -> ["system"]
  "auth failures" -> ["logs"]
  "processes" -> ["process"]
"""),
    ("human", "{question}"),
])

_chain = _prompt | _llm | JsonOutputParser()
VALID_GROUPS = {"system","cron","process","logs","prometheus","grafana","alerts","notification"}

def classifier_node(state: AgentState) -> dict:
    if state.get("mode") == "sweep":
        return {"intents": ["system","cron","prometheus","logs","grafana"]}
    question = state.get("question", "")
    if not question:
        return {"intents": ["system"]}
    try:
        raw = _chain.invoke({"question": question})
        intents = [i for i in raw if i in VALID_GROUPS]
        return {"intents": intents or ["system"]}
    except Exception as e:
        logger.warning(f"Classifier failed: {e}")
        return {"intents": ["system"]}
