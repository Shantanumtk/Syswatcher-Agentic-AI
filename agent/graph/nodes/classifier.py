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

Groups: system, cron, process, logs, prometheus, grafana, alerts, notification, rca, security, application

Examples:
  "is everything ok" -> ["system","cron","prometheus","logs"]
  "CPU usage" -> ["system","prometheus"]
  "cron jobs" -> ["cron","logs"]
  "alert rules" -> ["alerts"]
  "disk usage" -> ["system"]
  "auth failures" -> ["logs","security"]
  "processes" -> ["process"]
  "RCA report" -> ["rca","prometheus","grafana"]
  "root cause" -> ["rca","prometheus","grafana","logs"]
  "incident" -> ["rca","prometheus","grafana","logs"]
  "anomaly" -> ["prometheus","rca"]
  "baseline" -> ["rca","prometheus"]
  "security scan" -> ["security","logs"]
  "SSH attacks" -> ["security","logs"]
  "failed services" -> ["security","application"]
  "docker" -> ["application"]
  "is nginx running" -> ["application"]
  "port open" -> ["application","system"]
  "URL health" -> ["application"]
  "memory leak" -> ["prometheus","rca","system"]
  "disk IO" -> ["prometheus","system"]
  "network bandwidth" -> ["prometheus","system"]
  "compare servers" -> ["prometheus"]
  "iowait" -> ["prometheus","rca"]
  "SSL cert" -> ["security","application"]
  "firewall" -> ["security"]
  "kernel messages" -> ["logs"]
  "OOM" -> ["logs","rca"]
  "segfault" -> ["logs","rca"]
"""),
    ("human", "{question}"),
])

_chain = _prompt | _llm | JsonOutputParser()
VALID_GROUPS = {"system","cron","process","logs","prometheus","grafana","alerts","notification","rca","security","application"}

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
