import os
import requests
from datetime import datetime
from langchain_core.tools import tool

GRAFANA_URL   = os.getenv("GRAFANA_URL", "http://grafana:3000")
GRAFANA_TOKEN = os.getenv("GRAFANA_TOKEN", "")
GRAFANA_USER  = os.getenv("GRAFANA_ADMIN_USER", "admin")
GRAFANA_PASS  = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin123")

def _headers():
    if GRAFANA_TOKEN:
        return {"Authorization": f"Bearer {GRAFANA_TOKEN}", "Content-Type": "application/json"}
    # Fall back to basic auth during initial setup before token exists
    import base64
    creds = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASS}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

@tool
def post_grafana_annotation(text: str, severity: str = "warn") -> dict:
    """Post an annotation to Grafana marking a health event on the timeline.
    Call automatically when a warn or critical event is detected.
    severity: 'info' | 'warn' | 'critical'
    """
    tag_map = {
        "info":     ["syswatcher", "info"],
        "warn":     ["syswatcher", "warn"],
        "critical": ["syswatcher", "critical"],
    }
    payload = {
        "text": f"[SysWatcher] {text}",
        "tags": tag_map.get(severity, ["syswatcher"]),
        "time": int(datetime.now().timestamp() * 1000),
    }
    try:
        r = requests.post(
            f"{GRAFANA_URL}/api/annotations",
            json=payload, headers=_headers(), timeout=5
        )
        return {"status": r.status_code, "annotation_id": r.json().get("id")}
    except Exception as e:
        return {"error": str(e)}

@tool
def get_grafana_annotations(hours_back: int = 24) -> list:
    """Fetch recent SysWatcher annotations from Grafana.
    Use when asked: 'what events were flagged?', 'recent anomalies on Grafana'
    hours_back: how many hours to look back (default 24)
    """
    from_ms = int((datetime.now().timestamp() - hours_back * 3600) * 1000)
    try:
        r = requests.get(
            f"{GRAFANA_URL}/api/annotations",
            params={"tags": "syswatcher", "from": from_ms},
            headers=_headers(), timeout=5,
        )
        return [
            {"time": a.get("time"), "text": a.get("text"), "tags": a.get("tags")}
            for a in r.json()
        ]
    except Exception as e:
        return [{"error": str(e)}]
