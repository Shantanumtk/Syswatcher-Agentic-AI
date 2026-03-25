import os
import requests
from datetime import datetime, timedelta
from langchain_core.tools import tool

PROM_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")

def _prom_get(endpoint: str, params: dict) -> dict:
    try:
        r = requests.get(f"{PROM_URL}{endpoint}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return {"error": "cannot_connect", "detail": f"Prometheus unreachable at {PROM_URL}"}
    except requests.exceptions.Timeout:
        return {"error": "timeout", "detail": "Prometheus did not respond in 10s"}
    except Exception as e:
        return {"error": "http_error", "detail": str(e)}

def _safe_float(val: str):
    try:
        return float(val)
    except (ValueError, TypeError):
        return val

@tool
def query_prometheus_instant(promql: str) -> dict:
    """Query Prometheus for a current metric value using PromQL.
    Use when asked about RIGHT NOW values from Prometheus time series.

    Common PromQL expressions:
      CPU usage %       : 100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
      Memory used %     : 100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)
      Disk used % on /  : 100 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} * 100)
      Network rx bytes/s: rate(node_network_receive_bytes_total[5m])
      Load average 1m   : node_load1
      Load average 5m   : node_load5
    """
    raw = _prom_get("/api/v1/query", {"query": promql})
    if "error" in raw:
        return raw
    if raw.get("status") != "success":
        return {"error": "prometheus_error", "detail": raw.get("error", "unknown"), "promql": promql}

    results = raw["data"]["result"]
    if not results:
        return {"error": "no_data", "detail": "No data returned — metric may not exist yet", "promql": promql}

    if len(results) == 1:
        ts, val = results[0]["value"]
        return {
            "promql":  promql,
            "labels":  results[0]["metric"],
            "value":   _safe_float(val),
            "timestamp": ts,
        }

    return {
        "promql":       promql,
        "series_count": len(results),
        "results": [
            {"labels": r["metric"], "value": _safe_float(r["value"][1])}
            for r in results
        ],
    }

@tool
def query_prometheus_range(promql: str, hours_back: int = 1) -> dict:
    """Query Prometheus for metric history over a time range.
    Use for trend questions: 'how has CPU changed?', 'memory trend last hour'
    promql: PromQL expression
    hours_back: hours of history to fetch (default 1, max 24)
    """
    hours_back = min(hours_back, 24)
    end   = datetime.now()
    start = end - timedelta(hours=hours_back)
    raw   = _prom_get("/api/v1/query_range", {
        "query": promql,
        "start": start.timestamp(),
        "end":   end.timestamp(),
        "step":  "60",
    })
    if "error" in raw:
        return raw
    if raw.get("status") != "success":
        return {"error": "prometheus_error", "detail": raw.get("error")}

    results = raw["data"]["result"]
    if not results:
        return {"error": "no_data", "promql": promql}

    series = results[0]["values"]
    values = [_safe_float(v[1]) for v in series]

    return {
        "promql":     promql,
        "hours_back": hours_back,
        "points":     len(series),
        "min":        round(min(values), 2) if values else None,
        "max":        round(max(values), 2) if values else None,
        "avg":        round(sum(values) / len(values), 2) if values else None,
        "latest":     values[-1] if values else None,
        "trend":      "increasing" if len(values) > 1 and values[-1] > values[0] else "decreasing",
        "samples":    [{"t": v[0], "v": _safe_float(v[1])} for v in series[-10:]],
    }

@tool
def get_prometheus_alerts() -> list:
    """Get all currently firing Prometheus alerts.
    Use when asked: 'any alerts firing?', 'Prometheus alerts', 'active alerts'
    """
    raw = _prom_get("/api/v1/alerts", {})
    if "error" in raw:
        return [raw]
    if raw.get("status") != "success":
        return [{"error": "prometheus_error"}]

    firing = [
        {
            "name":     a["labels"].get("alertname"),
            "severity": a["labels"].get("severity"),
            "state":    a["state"],
            "summary":  a["annotations"].get("summary", ""),
        }
        for a in raw["data"]["alerts"]
        if a["state"] == "firing"
    ]
    return firing if firing else [{"info": "No alerts currently firing"}]
