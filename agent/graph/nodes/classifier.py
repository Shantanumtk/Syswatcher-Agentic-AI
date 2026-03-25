import logging
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from config import settings

logger = logging.getLogger("syswatcher.classifier")

_llm = ChatOpenAI(
    model=settings.llm_model,
    api_key=settings.openai_api_key,
    temperature=0,
)

_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an intent classifier for a server health agent.
Given a user question, return a JSON list of relevant tool groups.

Available groups:
- system      : CPU, memory, disk, network, load, uptime, open ports
- cron        : cron jobs, cron logs, scheduled tasks, cron failures
- process     : specific processes, zombies, process lookup
- logs        : log files, error patterns, auth failures, syslog
- prometheus  : metric history, trends, time-series queries
- grafana     : annotations, dashboard events
- alerts      : alert rules — create, list, remove
- notification: send Slack or email

Rules:
- Always return a JSON list, nothing else, no markdown.
- "full health check" or "is everything ok" -> ["system","cron","prometheus","logs"]
- "sweep" mode always -> ["system","cron","prometheus","logs","grafana"]
- CPU/memory/disk questions -> ["system","prometheus"]
- Cron questions -> ["cron","logs"]
- Alert setup questions -> ["alerts"]
- Process questions -> ["process"]
- Log questions -> ["logs"]

Examples:
  "What is CPU usage?"              -> ["system"]
  "Did backup cron run?"            -> ["cron","logs"]
  "Is memory trending up?"          -> ["prometheus"]
  "Add alert if disk > 80%"         -> ["alerts"]
  "Any auth failures today?"        -> ["logs"]
  "Is everything ok?"               -> ["system","cron","prometheus","logs"]
  "Which process is using CPU?"     -> ["system","process"]
"""),
    ("human", "{question}"),
])

_chain = _prompt | _llm | JsonOutputParser()

VALID_GROUPS = {"system","cron","process","logs","prometheus","grafana","alerts","notification"}

def classifier_node(state: AgentState) -> dict:
    from graph.state import AgentState

    # Sweep always uses full tool set
    if state.get("mode") == "sweep":
        return {"intents": ["system", "cron", "prometheus", "logs", "grafana"]}

    question = state.get("question", "")
    if not question:
        return {"intents": ["system"]}

    try:
        raw = _chain.invoke({"question": question})
        intents = [i for i in raw if i in VALID_GROUPS]
        if not intents:
            intents = ["system"]
        logger.info(f"Classified '{question[:60]}' -> {intents}")
        return {"intents": intents}
    except Exception as e:
        logger.warning(f"Classifier failed: {e} — defaulting to system")
        return {"intents": ["system"]}
