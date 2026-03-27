import os
import requests
from datetime import datetime, timedelta
from langchain_core.tools import tool

GRAFANA_URL  = os.getenv("GRAFANA_URL", "http://grafana:3000")
GRAFANA_USER = os.getenv("GRAFANA_ADMIN_USER", "admin")
GRAFANA_PASS = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin123")

def _headers():
    if os.getenv("GRAFANA_TOKEN"):
        return {"Authorization": f"Bearer {os.getenv('GRAFANA_TOKEN')}", "Content-Type": "application/json"}
    import base64
    creds = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASS}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

@tool
def post_grafana_annotation(text: str, severity: str = "warn") -> dict:
    """Post an annotation to Grafana marking a health event on the timeline.
    Call automatically when a warn or critical event is detected.
    severity: info | warn | critical
    """
    tag_map = {"info": ["syswatcher","info"], "warn": ["syswatcher","warn"], "critical": ["syswatcher","critical"]}
    payload = {"text": f"[SysWatcher] {text}", "tags": tag_map.get(severity, ["syswatcher"]), "time": int(datetime.now().timestamp() * 1000)}
    try:
        r = requests.post(f"{GRAFANA_URL}/api/annotations", json=payload, headers=_headers(), timeout=5)
        return {"status": r.status_code, "annotation_id": r.json().get("id")}
    except Exception as e:
        return {"error": str(e)}

@tool
def get_grafana_annotations(hours_back: int = 24) -> list:
    """Fetch recent SysWatcher annotations from Grafana.
    Use when asked: what events were flagged, recent anomalies on Grafana, event history
    hours_back: how many hours to look back (default 24)
    """
    from_ms = int((datetime.now().timestamp() - hours_back * 3600) * 1000)
    try:
        r = requests.get(f"{GRAFANA_URL}/api/annotations", params={"tags": "syswatcher", "from": from_ms}, headers=_headers(), timeout=5)
        return [{"time": a.get("time"), "text": a.get("text"), "tags": a.get("tags")} for a in r.json()]
    except Exception as e:
        return [{"error": str(e)}]

@tool
def get_annotations_timeline(hours_back: int = 6, server_name: str = None) -> dict:
    """Get a timeline of all SysWatcher events for incident investigation and RCA.
    Use when asked: what happened between X and Y, incident timeline, event sequence, RCA timeline
    hours_back: how far back to look (default 6)
    server_name: filter by server (optional)
    """
    from_ms = int((datetime.now().timestamp() - hours_back * 3600) * 1000)
    try:
        r = requests.get(f"{GRAFANA_URL}/api/annotations", params={"tags": "syswatcher", "from": from_ms, "limit": 100}, headers=_headers(), timeout=5)
        annotations = r.json()
        if server_name:
            annotations = [a for a in annotations if server_name.lower() in (a.get("text") or "").lower()]
        timeline = []
        for a in sorted(annotations, key=lambda x: x.get("time", 0)):
            ts = datetime.fromtimestamp(a["time"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
            tags = a.get("tags", [])
            severity = "critical" if "critical" in tags else "warn" if "warn" in tags else "info"
            timeline.append({"timestamp": ts, "severity": severity, "event": a.get("text", "").replace("[SysWatcher] ", "")})
        return {
            "hours_back": hours_back,
            "server_filter": server_name,
            "event_count": len(timeline),
            "timeline": timeline,
            "summary": f"{len([e for e in timeline if e['severity']=='critical'])} critical, {len([e for e in timeline if e['severity']=='warn'])} warn events in last {hours_back}h"
        }
    except Exception as e:
        return {"error": str(e)}

@tool
def get_grafana_dashboard_list() -> list:
    """List all available Grafana dashboards.
    Use when asked: what dashboards exist, list dashboards, show Grafana dashboards
    """
    try:
        r = requests.get(f"{GRAFANA_URL}/api/search?type=dash-db", headers=_headers(), timeout=5)
        return [{"id": d["id"], "title": d["title"], "url": GRAFANA_URL + d["url"], "tags": d.get("tags", [])} for d in r.json()]
    except Exception as e:
        return [{"error": str(e)}]

@tool
def get_grafana_health() -> dict:
    """Check if Grafana is healthy and accessible.
    Use when asked: is Grafana running, Grafana health, Grafana status
    """
    try:
        r = requests.get(f"{GRAFANA_URL}/api/health", headers=_headers(), timeout=5)
        data = r.json()
        return {"status": data.get("database", "unknown"), "version": data.get("version", "unknown"), "url": GRAFANA_URL, "healthy": r.status_code == 200}
    except Exception as e:
        return {"error": str(e), "healthy": False}
