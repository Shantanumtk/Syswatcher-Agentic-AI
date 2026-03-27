import os

files = {}

# ============================================================
# 1. prometheus_tools.py — extended with 7 new tools
# ============================================================
files["agent/tools/prometheus_tools.py"] = '''import os
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

def _safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return val

def _range_query(promql: str, hours_back: int = 1) -> dict:
    hours_back = min(hours_back, 24)
    end = datetime.now()
    start = end - timedelta(hours=hours_back)
    raw = _prom_get("/api/v1/query_range", {
        "query": promql, "start": start.timestamp(),
        "end": end.timestamp(), "step": "60",
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
        "promql": promql, "hours_back": hours_back,
        "points": len(series),
        "min": round(min(values), 2) if values else None,
        "max": round(max(values), 2) if values else None,
        "avg": round(sum(values) / len(values), 2) if values else None,
        "latest": values[-1] if values else None,
        "trend": "increasing" if len(values) > 1 and values[-1] > values[0] else "decreasing",
        "samples": [{"t": v[0], "v": _safe_float(v[1])} for v in series[-10:]],
    }

@tool
def query_prometheus_instant(promql: str) -> dict:
    """Query Prometheus for a current metric value using PromQL.
    Use when asked about RIGHT NOW values from Prometheus.
    Common queries: CPU%, memory%, disk%, network bytes/s, load average
    """
    raw = _prom_get("/api/v1/query", {"query": promql})
    if "error" in raw:
        return raw
    if raw.get("status") != "success":
        return {"error": "prometheus_error", "detail": raw.get("error", "unknown")}
    results = raw["data"]["result"]
    if not results:
        return {"error": "no_data", "promql": promql}
    if len(results) == 1:
        ts, val = results[0]["value"]
        return {"promql": promql, "labels": results[0]["metric"], "value": _safe_float(val), "timestamp": ts}
    return {"promql": promql, "series_count": len(results), "results": [{"labels": r["metric"], "value": _safe_float(r["value"][1])} for r in results]}

@tool
def query_prometheus_range(promql: str, hours_back: int = 1) -> dict:
    """Query Prometheus for metric history over a time range.
    Use for trend questions: how has CPU changed, memory trend last hour
    promql: PromQL expression
    hours_back: hours of history (default 1, max 24)
    """
    return _range_query(promql, hours_back)

@tool
def get_prometheus_alerts() -> list:
    """Get all currently firing Prometheus alerts.
    Use when asked: any alerts firing, Prometheus alerts, active alerts
    """
    raw = _prom_get("/api/v1/alerts", {})
    if "error" in raw:
        return [raw]
    firing = [
        {"name": a["labels"].get("alertname"), "severity": a["labels"].get("severity"),
         "state": a["state"], "summary": a["annotations"].get("summary", "")}
        for a in raw["data"]["alerts"] if a["state"] == "firing"
    ]
    return firing if firing else [{"info": "No alerts currently firing"}]

@tool
def get_cpu_trend(server_name: str = "local", hours_back: int = 3) -> dict:
    """Get CPU usage trend over time — detect patterns, spikes, gradual increase.
    Use when asked: has CPU been increasing, CPU pattern, CPU history, CPU after deployment
    server_name: local, dev, or test
    hours_back: hours of history (default 3, max 24)
    """
    label = "local" if server_name in ("local", "localhost") else server_name
    promql = f'100 - (avg by(server_name) (rate(node_cpu_seconds_total{{mode="idle",server_name="{label}"}}[5m])) * 100)'
    result = _range_query(promql, hours_back)
    result["server"] = server_name
    result["metric"] = "cpu_usage_pct"
    if isinstance(result.get("avg"), float):
        if result["trend"] == "increasing" and result["max"] - result["min"] > 10:
            result["alert"] = "CPU is trending upward significantly"
        elif result.get("max", 0) > 85:
            result["alert"] = f"CPU peaked at {result['max']}% in the last {hours_back}h"
        else:
            result["status"] = "CPU trend is normal"
    return result

@tool
def get_memory_trend(server_name: str = "local", hours_back: int = 3) -> dict:
    """Get memory usage trend — detect memory leaks, gradual growth.
    Use when asked: is memory leaking, memory growth, memory trend, memory increasing slowly
    server_name: local, dev, or test
    hours_back: hours of history (default 3, max 24)
    """
    label = "local" if server_name in ("local", "localhost") else server_name
    promql = f'100 * (1 - node_memory_MemAvailable_bytes{{server_name="{label}"}} / node_memory_MemTotal_bytes{{server_name="{label}"}})'
    result = _range_query(promql, hours_back)
    result["server"] = server_name
    result["metric"] = "memory_usage_pct"
    if isinstance(result.get("avg"), float):
        growth = (result.get("latest", 0) or 0) - (result.get("samples", [{}])[0].get("v", 0) or 0)
        result["growth_pct"] = round(growth, 2)
        if growth > 10:
            result["alert"] = f"Memory grew by {growth:.1f}% — possible memory leak"
        elif result.get("max", 0) > 90:
            result["alert"] = f"Memory peaked at {result['max']}%"
        else:
            result["status"] = "Memory trend is normal"
    return result

@tool
def get_disk_io_rate(server_name: str = "local") -> dict:
    """Get real-time disk read/write speed in MB/s and IOPS.
    Use when asked: disk I/O speed, read write speed, disk throughput, is disk the bottleneck
    server_name: local, dev, or test
    """
    label = "local" if server_name in ("local", "localhost") else server_name
    read_promql = f'rate(node_disk_read_bytes_total{{server_name="{label}"}}[5m])'
    write_promql = f'rate(node_disk_written_bytes_total{{server_name="{label}"}}[5m])'
    reads_raw = _prom_get("/api/v1/query", {"query": read_promql})
    writes_raw = _prom_get("/api/v1/query", {"query": write_promql})

    def _sum_results(raw):
        if raw.get("status") != "success":
            return 0
        return sum(_safe_float(r["value"][1]) for r in raw["data"]["result"] if isinstance(_safe_float(r["value"][1]), float))

    read_bps = _sum_results(reads_raw)
    write_bps = _sum_results(writes_raw)
    return {
        "server": server_name,
        "read_mbps": round(read_bps / 1e6, 3),
        "write_mbps": round(write_bps / 1e6, 3),
        "read_kbps": round(read_bps / 1e3, 1),
        "write_kbps": round(write_bps / 1e3, 1),
        "status": "high" if (read_bps + write_bps) > 100e6 else "normal",
        "note": "Values are 5-minute averages"
    }

@tool
def get_network_bandwidth(server_name: str = "local") -> dict:
    """Get real-time network bandwidth in Mbps (receive and transmit).
    Use when asked: network speed, bandwidth usage, network throughput, how much data is being transferred
    server_name: local, dev, or test
    """
    label = "local" if server_name in ("local", "localhost") else server_name
    rx_promql = f'rate(node_network_receive_bytes_total{{server_name="{label}",device!~"lo|docker.*|br.*"}}[5m])'
    tx_promql = f'rate(node_network_transmit_bytes_total{{server_name="{label}",device!~"lo|docker.*|br.*"}}[5m])'
    rx_raw = _prom_get("/api/v1/query", {"query": rx_promql})
    tx_raw = _prom_get("/api/v1/query", {"query": tx_promql})

    def _parse(raw):
        if raw.get("status") != "success":
            return {}
        result = {}
        for r in raw["data"]["result"]:
            dev = r["metric"].get("device", "unknown")
            val = _safe_float(r["value"][1])
            result[dev] = round(val / 1e6 * 8, 3) if isinstance(val, float) else 0
        return result

    rx = _parse(rx_raw)
    tx = _parse(tx_raw)
    total_rx = sum(rx.values())
    total_tx = sum(tx.values())
    return {
        "server": server_name,
        "total_rx_mbps": round(total_rx, 3),
        "total_tx_mbps": round(total_tx, 3),
        "per_interface_rx_mbps": rx,
        "per_interface_tx_mbps": tx,
        "status": "high" if total_rx + total_tx > 100 else "normal",
        "note": "Values in Mbps (megabits per second), 5-min average"
    }

@tool
def get_cpu_iowait(server_name: str = "local") -> dict:
    """Get CPU I/O wait percentage — time CPU spends waiting for disk.
    High iowait means disk is the bottleneck, not CPU.
    Use when asked: is disk causing CPU issues, iowait, CPU waiting for disk, disk bottleneck
    server_name: local, dev, or test
    """
    label = "local" if server_name in ("local", "localhost") else server_name
    promql = f'avg by(server_name) (rate(node_cpu_seconds_total{{mode="iowait",server_name="{label}"}}[5m])) * 100'
    raw = _prom_get("/api/v1/query", {"query": promql})
    if raw.get("status") != "success":
        return {"error": "Could not fetch iowait", "server": server_name}
    results = raw["data"]["result"]
    iowait = _safe_float(results[0]["value"][1]) if results else 0
    iowait = round(iowait, 2) if isinstance(iowait, float) else 0
    return {
        "server": server_name,
        "iowait_pct": iowait,
        "status": "critical" if iowait > 20 else "warn" if iowait > 10 else "normal",
        "interpretation": (
            "Disk I/O is severely bottlenecking CPU" if iowait > 20
            else "Disk I/O is causing some CPU delay" if iowait > 10
            else "CPU is not waiting for disk — disk is not the bottleneck"
        )
    }

@tool
def compare_server_metrics(metric: str = "cpu") -> dict:
    """Compare the same metric across all monitored servers simultaneously.
    Use when asked: compare CPU across servers, which server is most loaded, server comparison
    metric: cpu, memory, disk, load, network
    """
    queries = {
        "cpu": '100 - (avg by(server_name) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
        "memory": '100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)',
        "disk": '100 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} * 100)',
        "load": "node_load1",
        "network": 'rate(node_network_receive_bytes_total{device!~"lo|docker.*"}[5m]) * 8 / 1e6',
    }
    promql = queries.get(metric, queries["cpu"])
    raw = _prom_get("/api/v1/query", {"query": promql})
    if raw.get("status") != "success":
        return {"error": f"Could not query {metric}"}
    results = {}
    for r in raw["data"]["result"]:
        server = r["metric"].get("server_name", r["metric"].get("instance", "unknown"))
        val = _safe_float(r["value"][1])
        results[server] = round(val, 2) if isinstance(val, float) else val
    if not results:
        return {"error": "No data", "metric": metric}
    sorted_results = dict(sorted(results.items(), key=lambda x: x[1] if isinstance(x[1], float) else 0, reverse=True))
    highest = max(results, key=lambda k: results[k] if isinstance(results[k], float) else 0)
    return {
        "metric": metric,
        "comparison": sorted_results,
        "highest": highest,
        "highest_value": results[highest],
        "unit": "%" if metric in ("cpu", "memory", "disk") else "Mbps" if metric == "network" else "load",
    }

@tool
def get_prometheus_targets() -> dict:
    """Check which servers Prometheus is actively scraping and their health.
    Use when asked: is server being monitored, scrape targets, which servers are monitored, prometheus targets
    """
    raw = _prom_get("/api/v1/targets", {})
    if "error" in raw:
        return raw
    targets = raw.get("data", {}).get("activeTargets", [])
    result = {"up": [], "down": [], "total": len(targets)}
    for t in targets:
        info = {
            "job": t["labels"].get("job", "unknown"),
            "instance": t["labels"].get("instance", "unknown"),
            "server_name": t["labels"].get("server_name", "unknown"),
            "health": t["health"],
            "last_scrape": t.get("lastScrape", ""),
            "error": t.get("lastError", ""),
        }
        if t["health"] == "up":
            result["up"].append(info)
        else:
            result["down"].append(info)
    result["status"] = "all_healthy" if not result["down"] else f"{len(result['down'])} target(s) down"
    return result

@tool
def get_metric_anomaly(server_name: str = "local", metric: str = "cpu") -> dict:
    """Detect sudden spikes or anomalies in metrics compared to recent baseline.
    Use when asked: any anomalies, sudden spikes, unusual activity, metric anomaly
    server_name: local, dev, or test
    metric: cpu, memory, disk, network
    """
    label = "local" if server_name in ("local", "localhost") else server_name
    queries = {
        "cpu": f'100 - (avg by(server_name) (rate(node_cpu_seconds_total{{mode="idle",server_name="{label}"}}[5m])) * 100)',
        "memory": f'100 * (1 - node_memory_MemAvailable_bytes{{server_name="{label}"}} / node_memory_MemTotal_bytes{{server_name="{label}"}})',
        "disk": f'100 - (node_filesystem_avail_bytes{{server_name="{label}",mountpoint="/"}} / node_filesystem_size_bytes{{server_name="{label}",mountpoint="/"}} * 100)',
        "network": f'rate(node_network_receive_bytes_total{{server_name="{label}",device!~"lo"}}[5m]) * 8 / 1e6',
    }
    promql = queries.get(metric, queries["cpu"])
    result_1h = _range_query(promql, 1)
    result_6h = _range_query(promql, 6)
    if "error" in result_1h or "error" in result_6h:
        return {"error": "Could not fetch metric data", "server": server_name}
    recent_avg = result_1h.get("avg", 0) or 0
    baseline_avg = result_6h.get("avg", 0) or 0
    recent_max = result_1h.get("max", 0) or 0
    deviation = recent_avg - baseline_avg
    anomaly = abs(deviation) > (baseline_avg * 0.3) if baseline_avg > 0 else False
    return {
        "server": server_name,
        "metric": metric,
        "recent_1h_avg": round(recent_avg, 2),
        "baseline_6h_avg": round(baseline_avg, 2),
        "recent_max": round(recent_max, 2),
        "deviation": round(deviation, 2),
        "anomaly_detected": anomaly,
        "severity": "critical" if abs(deviation) > baseline_avg * 0.5 else "warn" if anomaly else "normal",
        "interpretation": (
            f"ANOMALY: {metric} is {abs(deviation):.1f}% {'above' if deviation > 0 else 'below'} baseline"
            if anomaly else f"{metric} is within normal range (deviation: {deviation:.1f}%)"
        )
    }
'''

# ============================================================
# 2. grafana_tools.py — extended with 5 new tools
# ============================================================
files["agent/tools/grafana_tools.py"] = '''import os
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
'''

# ============================================================
# 3. rca_tools.py — NEW FILE
# ============================================================
files["agent/tools/rca_tools.py"] = '''import os
import requests
from datetime import datetime, timedelta
from langchain_core.tools import tool

PROM_URL    = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://grafana:3000")
GRAFANA_USER = os.getenv("GRAFANA_ADMIN_USER", "admin")
GRAFANA_PASS = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin123")

def _prom(promql, hours_back=1):
    end = datetime.now()
    start = end - timedelta(hours=hours_back)
    try:
        r = requests.get(f"{PROM_URL}/api/v1/query_range", params={"query": promql, "start": start.timestamp(), "end": end.timestamp(), "step": "60"}, timeout=10)
        data = r.json()
        if data.get("status") != "success" or not data["data"]["result"]:
            return None
        values = [float(v[1]) for v in data["data"]["result"][0]["values"] if v[1] != "NaN"]
        return {"avg": round(sum(values)/len(values), 2), "max": round(max(values), 2), "min": round(min(values), 2), "latest": round(values[-1], 2)} if values else None
    except Exception:
        return None

def _grafana_headers():
    import base64
    creds = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASS}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

@tool
def get_rca_report(server_name: str = "local", hours_back: int = 2) -> dict:
    """Generate a full Root Cause Analysis (RCA) report for a server.
    Combines CPU, memory, disk I/O, network, and event timeline to identify what caused an incident.
    Use when asked: what caused the incident, RCA report, root cause analysis, why was server slow,
    what happened at 3pm, investigate the issue
    server_name: local, dev, or test
    hours_back: how far back to analyze (default 2 hours)
    """
    label = "local" if server_name in ("local", "localhost") else server_name
    report = {
        "server": server_name,
        "analysis_period": f"Last {hours_back} hours",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "metrics": {},
        "findings": [],
        "recommendations": [],
        "severity": "healthy",
    }

    # CPU analysis
    cpu_data = _prom(f'100 - (avg by(server_name) (rate(node_cpu_seconds_total{{mode="idle",server_name="{label}"}}[5m])) * 100)', hours_back)
    if cpu_data:
        report["metrics"]["cpu"] = cpu_data
        if cpu_data["max"] > 90:
            report["findings"].append(f"CRITICAL: CPU peaked at {cpu_data['max']}% (avg {cpu_data['avg']}%)")
            report["recommendations"].append("Identify top CPU-consuming processes and consider scaling or optimizing")
            report["severity"] = "critical"
        elif cpu_data["max"] > 75:
            report["findings"].append(f"WARN: CPU was elevated, peaked at {cpu_data['max']}% (avg {cpu_data['avg']}%)")
            report["severity"] = "warn" if report["severity"] == "healthy" else report["severity"]

    # Memory analysis
    mem_data = _prom(f'100 * (1 - node_memory_MemAvailable_bytes{{server_name="{label}"}} / node_memory_MemTotal_bytes{{server_name="{label}"}})', hours_back)
    if mem_data:
        report["metrics"]["memory"] = mem_data
        growth = mem_data["latest"] - mem_data["min"]
        if mem_data["max"] > 90:
            report["findings"].append(f"CRITICAL: Memory peaked at {mem_data['max']}%")
            report["recommendations"].append("Check for memory leaks — memory grew by {:.1f}%".format(growth))
            report["severity"] = "critical"
        elif growth > 15:
            report["findings"].append(f"WARN: Memory grew by {growth:.1f}% during the period — possible memory leak")
            report["severity"] = "warn" if report["severity"] == "healthy" else report["severity"]

    # I/O wait analysis
    iowait_data = _prom(f'avg by(server_name) (rate(node_cpu_seconds_total{{mode="iowait",server_name="{label}"}}[5m])) * 100', hours_back)
    if iowait_data:
        report["metrics"]["iowait"] = iowait_data
        if iowait_data["max"] > 20:
            report["findings"].append(f"CRITICAL: I/O wait peaked at {iowait_data['max']}% — disk is bottleneck")
            report["recommendations"].append("Disk I/O is causing CPU stalls — check disk read/write rates and optimize disk-heavy operations")
            report["severity"] = "critical"
        elif iowait_data["avg"] > 10:
            report["findings"].append(f"WARN: I/O wait averaged {iowait_data['avg']}% — disk under pressure")

    # Disk usage analysis
    disk_data = _prom(f'100 - (node_filesystem_avail_bytes{{server_name="{label}",mountpoint="/"}} / node_filesystem_size_bytes{{server_name="{label}",mountpoint="/"}} * 100)', hours_back)
    if disk_data:
        report["metrics"]["disk"] = disk_data
        if disk_data["max"] > 90:
            report["findings"].append(f"CRITICAL: Disk usage at {disk_data['max']}% — nearly full")
            report["recommendations"].append("Free disk space immediately — delete old logs, backups, or expand volume")
            report["severity"] = "critical"

    # Network analysis
    net_data = _prom(f'rate(node_network_receive_bytes_total{{server_name="{label}",device!~"lo|docker.*"}}[5m]) * 8 / 1e6', hours_back)
    if net_data:
        report["metrics"]["network_rx_mbps"] = net_data
        if net_data["max"] > 800:
            report["findings"].append(f"WARN: Network receive peaked at {net_data['max']:.1f} Mbps — possible traffic spike")

    # Load average analysis
    load_data = _prom(f'node_load1{{server_name="{label}"}}', hours_back)
    if load_data:
        report["metrics"]["load_avg"] = load_data
        if load_data["max"] > 4:
            report["findings"].append(f"CRITICAL: Load average peaked at {load_data['max']} — system was severely overloaded")
            report["severity"] = "critical"

    # Grafana annotations (events during this period)
    try:
        from_ms = int((datetime.now().timestamp() - hours_back * 3600) * 1000)
        import base64
        creds = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASS}".encode()).decode()
        headers = {"Authorization": f"Basic {creds}"}
        r = requests.get(f"{GRAFANA_URL}/api/annotations", params={"tags": "syswatcher", "from": from_ms, "limit": 50}, headers=headers, timeout=5)
        annotations = r.json()
        events = [{"time": datetime.fromtimestamp(a["time"]/1000).strftime("%H:%M:%S"), "text": a.get("text","").replace("[SysWatcher] ","")} for a in annotations if server_name in a.get("text","")]
        if events:
            report["events_during_period"] = events
            report["findings"].append(f"Found {len(events)} SysWatcher events during this period")
    except Exception:
        pass

    # Final summary
    if not report["findings"]:
        report["findings"].append("No significant issues found during this period")
        report["summary"] = f"Server {server_name} was healthy during the last {hours_back} hours"
    else:
        report["summary"] = f"Found {len(report['findings'])} issue(s) on {server_name} — severity: {report['severity'].upper()}"

    if not report["recommendations"]:
        report["recommendations"].append("No immediate action required — continue monitoring")

    return report

@tool
def get_system_baseline(server_name: str = "local") -> dict:
    """Compare current metrics against 24-hour baseline to detect deviations.
    Use when asked: is this normal, compare to baseline, how does current compare to usual, any deviations
    server_name: local, dev, or test
    """
    label = "local" if server_name in ("local", "localhost") else server_name
    metrics = {
        "cpu": f'100 - (avg by(server_name) (rate(node_cpu_seconds_total{{mode="idle",server_name="{label}"}}[5m])) * 100)',
        "memory": f'100 * (1 - node_memory_MemAvailable_bytes{{server_name="{label}"}} / node_memory_MemTotal_bytes{{server_name="{label}"}})',
        "load": f'node_load1{{server_name="{label}"}}',
    }

    result = {"server": server_name, "baseline_hours": 24, "current_vs_baseline": {}, "deviations": []}

    for metric_name, promql in metrics.items():
        current = _prom(promql, 1)
        baseline = _prom(promql, 24)
        if current and baseline:
            deviation = current["avg"] - baseline["avg"]
            pct_change = (deviation / baseline["avg"] * 100) if baseline["avg"] > 0 else 0
            result["current_vs_baseline"][metric_name] = {
                "current_avg": current["avg"],
                "baseline_avg": baseline["avg"],
                "deviation": round(deviation, 2),
                "pct_change": round(pct_change, 1),
                "status": "elevated" if pct_change > 20 else "low" if pct_change < -20 else "normal"
            }
            if abs(pct_change) > 20:
                result["deviations"].append(f"{metric_name} is {abs(pct_change):.0f}% {'above' if pct_change > 0 else 'below'} 24h baseline")

    result["summary"] = f"{len(result['deviations'])} deviation(s) from baseline" if result["deviations"] else "All metrics within normal baseline range"
    return result
'''

# ============================================================
# 4. security_tools.py — NEW FILE
# ============================================================
files["agent/tools/security_tools.py"] = '''import os
import subprocess
import paramiko
from langchain_core.tools import tool

def _get_server_ssh(server_name: str):
    conf_path = "/app/syswatcher.conf"
    if os.path.exists(conf_path):
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    if key.strip() == server_name:
                        parts = val.strip().split()
                        if len(parts) >= 3:
                            return parts[0], parts[1], parts[2]
    try:
        import psycopg2
        db_url = os.getenv("DATABASE_URL", "")
        if db_url:
            conn = psycopg2.connect(db_url)
            cur = conn.cursor()
            cur.execute("SELECT ip, ssh_user, ssh_key_path FROM servers WHERE name=%s AND active=true", (server_name,))
            row = cur.fetchone()
            conn.close()
            if row:
                return row[0], row[1], row[2]
    except Exception:
        pass
    return None, None, None

def _run(server_name: str, cmd: str, timeout: int = 10) -> str:
    if server_name in ("local", "localhost", ""):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return r.stdout + r.stderr
        except Exception as e:
            return str(e)
    ip, user, key_path = _get_server_ssh(server_name)
    if not ip:
        return f"Server {server_name} not found"
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=user, key_filename=key_path, timeout=8, banner_timeout=8)
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode() + stderr.read().decode()
        client.close()
        return out
    except Exception as e:
        return f"SSH error: {e}"

@tool
def get_failed_ssh_attempts(server_name: str = "local", limit: int = 20) -> list:
    """Get recent failed SSH login attempts — detect brute force attacks.
    Use when asked: SSH attacks, brute force, failed logins, who tried to login, unauthorized access
    server_name: local, dev, or test
    limit: number of recent attempts to return
    """
    out = _run(server_name, f"grep 'Failed password\\|Invalid user\\|authentication failure' /var/log/auth.log 2>/dev/null | tail -{limit} || journalctl _SYSTEMD_UNIT=sshd.service -n {limit} --no-pager -p warning 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No failed SSH attempts found"]

@tool
def get_active_sessions(server_name: str = "local") -> list:
    """Get currently logged in users and their sessions.
    Use when asked: who is logged in, active sessions, current users, who is on the server
    server_name: local, dev, or test
    """
    out = _run(server_name, "who && echo '---' && last -n 5 2>/dev/null | head -10")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No active sessions found"]

@tool
def get_sudo_history(server_name: str = "local", limit: int = 20) -> list:
    """Get recent sudo command usage — audit privileged operations.
    Use when asked: sudo history, privileged commands, what sudo commands were run, admin activity
    server_name: local, dev, or test
    """
    out = _run(server_name, f"grep 'sudo' /var/log/auth.log 2>/dev/null | tail -{limit} || journalctl _COMM=sudo -n {limit} --no-pager 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No sudo history found"]

@tool
def get_firewall_rules(server_name: str = "local") -> dict:
    """Get active firewall rules (UFW or iptables).
    Use when asked: firewall rules, open ports in firewall, UFW rules, iptables rules, what is blocked
    server_name: local, dev, or test
    """
    ufw = _run(server_name, "ufw status numbered 2>/dev/null || echo 'UFW not available'")
    iptables = _run(server_name, "iptables -L INPUT -n --line-numbers 2>/dev/null | head -30 || echo 'iptables not available'")
    return {
        "server": server_name,
        "ufw": [l.strip() for l in ufw.splitlines() if l.strip()],
        "iptables_input": [l.strip() for l in iptables.splitlines() if l.strip()],
    }

@tool
def get_ssl_cert_expiry(server_name: str = "local", domains: list = None) -> list:
    """Check SSL certificate expiry dates for domains or local certs.
    Use when asked: SSL cert expiry, certificate expiry, when does cert expire, SSL check
    server_name: local, dev, or test
    domains: list of domains to check (optional)
    """
    results = []
    if domains:
        for domain in domains:
            out = _run(server_name, f"echo | openssl s_client -servername {domain} -connect {domain}:443 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null")
            results.append({"domain": domain, "expiry": out.strip() or "Could not check"})
    else:
        out = _run(server_name, "find /etc/ssl /etc/nginx /etc/letsencrypt -name '*.crt' -o -name '*.pem' 2>/dev/null | head -10 | xargs -I{} openssl x509 -noout -enddate -subject -in {} 2>/dev/null")
        results = [{"cert": l.strip()} for l in out.splitlines() if l.strip()] or [{"info": "No SSL certs found in standard locations"}]
    return results

@tool
def get_listening_services(server_name: str = "local") -> list:
    """Get all services listening on network ports with process ownership.
    Use when asked: what services are running, listening services, what is on port X, service audit
    server_name: local, dev, or test
    """
    out = _run(server_name, "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip() and "LISTEN" in l]
    parsed = []
    for line in lines:
        parts = line.split()
        parsed.append({"local_address": parts[3] if len(parts) > 3 else "", "process": parts[-1] if parts else "", "raw": line})
    return parsed if parsed else [{"info": "No listening services found"}]

@tool
def get_recent_logins(server_name: str = "local", limit: int = 10) -> list:
    """Get recent successful login history.
    Use when asked: recent logins, login history, who logged in, last logins
    server_name: local, dev, or test
    """
    out = _run(server_name, f"last -n {limit} --time-format iso 2>/dev/null | head -{limit+2}")
    lines = [l.strip() for l in out.splitlines() if l.strip() and "wtmp" not in l]
    return lines if lines else ["No login history found"]

@tool
def get_world_writable_files(server_name: str = "local") -> list:
    """Find world-writable files and directories — security misconfiguration risk.
    Use when asked: world writable files, security scan, file permissions, insecure files
    server_name: local, dev, or test
    """
    out = _run(server_name, "find /etc /usr /var -maxdepth 3 -perm -o+w -not -path '*/proc/*' 2>/dev/null | head -20", timeout=15)
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No world-writable files found in standard locations — good"]

@tool
def get_failed_services(server_name: str = "local") -> list:
    """Get all failed systemd services.
    Use when asked: failed services, what services crashed, broken services, systemd failures
    server_name: local, dev, or test
    """
    out = _run(server_name, "systemctl --failed --no-legend 2>/dev/null | head -20")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No failed services — all services are running"]

@tool
def get_service_status(server_name: str = "local", service: str = "nginx") -> dict:
    """Check status of a specific systemd service.
    Use when asked: is nginx running, check apache status, is postgres up, service health check
    server_name: local, dev, or test
    service: service name e.g. nginx, apache2, postgresql, redis, docker
    """
    out = _run(server_name, f"systemctl is-active {service} 2>/dev/null && systemctl status {service} --no-pager -l 2>/dev/null | head -20")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    active = "active" in (lines[0] if lines else "")
    return {"server": server_name, "service": service, "active": active, "status": lines[0] if lines else "unknown", "details": lines[1:10]}
'''

# ============================================================
# 5. log_tools.py — extended with 8 new tools
# ============================================================
files["agent/tools/log_tools.py"] = '''import subprocess
from langchain_core.tools import tool
import os
import paramiko

def _get_server_ssh(server_name: str):
    conf_path = "/app/syswatcher.conf"
    if os.path.exists(conf_path):
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    if key.strip() == server_name:
                        parts = val.strip().split()
                        if len(parts) >= 3:
                            return parts[0], parts[1], parts[2]
    return None, None, None

def _run(server_name: str, cmd: str, timeout: int = 10) -> str:
    if server_name in ("local", "localhost", ""):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return r.stdout + r.stderr
        except Exception as e:
            return str(e)
    ip, user, key_path = _get_server_ssh(server_name)
    if not ip:
        return f"Server {server_name} not found"
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=user, key_filename=key_path, timeout=8, banner_timeout=8)
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode() + stderr.read().decode()
        client.close()
        return out
    except Exception as e:
        return f"SSH error: {e}"

@tool
def tail_log_file(path: str, lines: int = 50, server_name: str = "local") -> list:
    """Read the last N lines from a log file.
    Use when asked: show logs, tail log file, last lines of log
    path: full path to log file
    lines: number of lines (default 50)
    server_name: local, dev, or test
    """
    lines = min(lines, 200)
    out = _run(server_name, f"tail -{lines} {path} 2>&1")
    if "No such file" in out:
        return [f"File not found: {path}"]
    return [l for l in out.splitlines() if l.strip()]

@tool
def search_log_pattern(path: str, pattern: str, lines: int = 50, server_name: str = "local") -> list:
    """Search a log file for a pattern (grep).
    Use when asked: find errors in log, search for X in log, grep log
    path: log file path
    pattern: search term e.g. ERROR, connection refused, 500
    server_name: local, dev, or test
    """
    out = _run(server_name, f"grep -i '{pattern}' {path} 2>&1 | tail -{lines}")
    if "No such file" in out:
        return [f"File not found: {path}"]
    results = [l for l in out.splitlines() if l.strip()]
    return results if results else [f"No matches for '{pattern}' in {path}"]

@tool
def get_auth_failures(server_name: str = "local", hours_back: int = 24) -> list:
    """Get recent authentication failures from auth logs.
    Use when asked: auth failures, failed logins, SSH attacks, brute force
    server_name: local, dev, or test
    """
    out = _run(server_name, "grep -i 'failed\\|invalid\\|authentication failure' /var/log/auth.log 2>/dev/null | tail -50 || journalctl _SYSTEMD_UNIT=sshd.service --no-pager -n 50 -p warning 2>/dev/null")
    results = [l.strip() for l in out.splitlines() if l.strip()]
    return results if results else ["No auth failures found"]

@tool
def get_error_summary(server_name: str = "local", log_path: str = "/var/log/syslog") -> dict:
    """Get a summary of errors grouped by type and count.
    Use when asked: error summary, what errors are happening, group errors, error analysis
    server_name: local, dev, or test
    log_path: log file to analyze (default: /var/log/syslog)
    """
    out = _run(server_name, f"grep -i 'error\\|critical\\|fatal\\|panic' {log_path} 2>/dev/null | tail -200")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    error_counts = {}
    for line in lines:
        words = line.split()
        key = " ".join(words[4:8]) if len(words) >= 8 else line[:60]
        error_counts[key] = error_counts.get(key, 0) + 1
    sorted_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    return {
        "server": server_name,
        "log_path": log_path,
        "total_errors": len(lines),
        "unique_error_types": len(error_counts),
        "top_errors": [{"pattern": k, "count": v} for k, v in sorted_errors],
    }

@tool
def get_oom_events(server_name: str = "local") -> list:
    """Get Out Of Memory (OOM) killer events — processes killed due to low memory.
    Use when asked: OOM events, out of memory, process killed by kernel, memory killer
    server_name: local, dev, or test
    """
    out = _run(server_name, "grep -i 'oom\\|out of memory\\|killed process' /var/log/syslog 2>/dev/null | tail -20 || dmesg 2>/dev/null | grep -i 'oom\\|killed' | tail -20")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No OOM events found — memory is healthy"]

@tool
def get_kernel_messages(server_name: str = "local", limit: int = 30) -> list:
    """Get kernel messages (dmesg) — hardware errors, driver issues, OOM events.
    Use when asked: kernel messages, hardware errors, dmesg, kernel logs, system errors
    server_name: local, dev, or test
    """
    out = _run(server_name, f"dmesg --time-format iso 2>/dev/null | tail -{limit} || dmesg | tail -{limit}")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No kernel messages available"]

@tool
def get_application_errors(server_name: str = "local", pattern: str = "error", logs: list = None) -> dict:
    """Search multiple log files simultaneously for errors.
    Use when asked: application errors, search all logs, find errors across logs, multi-log search
    server_name: local, dev, or test
    pattern: error pattern to search (default: error)
    logs: list of log paths (default: common log locations)
    """
    if not logs:
        logs = ["/var/log/syslog", "/var/log/nginx/error.log", "/var/log/apache2/error.log", "/var/log/auth.log"]
    results = {}
    for log_path in logs:
        out = _run(server_name, f"grep -i '{pattern}' {log_path} 2>/dev/null | tail -10")
        lines = [l.strip() for l in out.splitlines() if l.strip() and "No such file" not in l]
        if lines:
            results[log_path] = lines
    return {"server": server_name, "pattern": pattern, "results": results, "total_matches": sum(len(v) for v in results.values())}

@tool
def get_log_volume_trend(server_name: str = "local", log_path: str = "/var/log/syslog") -> dict:
    """Check how fast a log file is growing — detect log explosion.
    Use when asked: log growth, log size, log explosion, disk filling from logs
    server_name: local, dev, or test
    log_path: log file to check
    """
    out = _run(server_name, f"ls -lh {log_path} 2>/dev/null && wc -l {log_path} 2>/dev/null && stat -c '%s %y' {log_path} 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return {"server": server_name, "log_path": log_path, "info": lines}

@tool
def get_segfault_events(server_name: str = "local") -> list:
    """Get segmentation fault events — application crashes.
    Use when asked: segfaults, application crashes, core dumps, process crashes
    server_name: local, dev, or test
    """
    out = _run(server_name, "grep -i 'segfault\\|segmentation fault\\|core dump' /var/log/syslog 2>/dev/null | tail -20 || dmesg 2>/dev/null | grep -i 'segfault' | tail -20")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines if lines else ["No segfault events found"]
'''

# ============================================================
# 6. application_tools.py — NEW FILE
# ============================================================
files["agent/tools/application_tools.py"] = '''import os
import subprocess
import paramiko
import requests
import socket
from langchain_core.tools import tool

def _get_server_ssh(server_name: str):
    conf_path = "/app/syswatcher.conf"
    if os.path.exists(conf_path):
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    if key.strip() == server_name:
                        parts = val.strip().split()
                        if len(parts) >= 3:
                            return parts[0], parts[1], parts[2]
    return None, None, None

def _run(server_name: str, cmd: str, timeout: int = 10) -> str:
    if server_name in ("local", "localhost", ""):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return r.stdout + r.stderr
        except Exception as e:
            return str(e)
    ip, user, key_path = _get_server_ssh(server_name)
    if not ip:
        return f"Server {server_name} not found"
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=user, key_filename=key_path, timeout=8, banner_timeout=8)
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode() + stderr.read().decode()
        client.close()
        return out
    except Exception as e:
        return f"SSH error: {e}"

@tool
def check_port_open(server_name: str = "local", port: int = 80, host: str = "localhost") -> dict:
    """Check if a specific port is open and responding.
    Use when asked: is port X open, check port 3000, is service on port X, port connectivity
    server_name: local, dev, or test
    port: port number to check
    host: host to check (default: localhost)
    """
    out = _run(server_name, f"nc -zv -w3 {host} {port} 2>&1 || (echo | timeout 3 bash -c 'cat < /dev/null > /dev/tcp/{host}/{port}' 2>&1 && echo 'open' || echo 'closed')")
    is_open = "open" in out.lower() or "succeeded" in out.lower() or "connected" in out.lower()
    return {"server": server_name, "host": host, "port": port, "open": is_open, "response": out.strip()[:200]}

@tool
def check_url_health(url: str, expected_status: int = 200, timeout: int = 10) -> dict:
    """Check if a URL is healthy and returning expected status code.
    Use when asked: is website up, check URL health, HTTP health check, is endpoint responding
    url: full URL to check e.g. http://localhost:8000/health
    expected_status: expected HTTP status code (default 200)
    timeout: timeout in seconds (default 10)
    """
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        return {
            "url": url,
            "status_code": r.status_code,
            "healthy": r.status_code == expected_status,
            "response_time_ms": round(r.elapsed.total_seconds() * 1000, 2),
            "content_length": len(r.content),
            "headers": dict(list(r.headers.items())[:5]),
        }
    except requests.exceptions.ConnectionError:
        return {"url": url, "healthy": False, "error": "Connection refused — service may be down"}
    except requests.exceptions.Timeout:
        return {"url": url, "healthy": False, "error": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"url": url, "healthy": False, "error": str(e)}

@tool
def check_process_alive(server_name: str = "local", process_name: str = "nginx") -> dict:
    """Check if a named process is running.
    Use when asked: is nginx running, is postgres alive, check if process X is up
    server_name: local, dev, or test
    process_name: process name to check e.g. nginx, postgres, redis-server, docker
    """
    out = _run(server_name, f"pgrep -a {process_name} 2>/dev/null | head -5 || ps aux | grep -v grep | grep {process_name} | head -5")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    is_running = bool(lines) and "SSH error" not in out
    return {
        "server": server_name,
        "process": process_name,
        "running": is_running,
        "instances": len(lines),
        "details": lines[:5],
    }

@tool
def get_docker_containers(server_name: str = "local") -> list:
    """List all Docker containers and their status.
    Use when asked: list containers, docker containers, what containers are running, docker status
    server_name: local, dev, or test
    """
    out = _run(server_name, "docker ps -a --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\\t{{.Image}}' 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if "command not found" in out.lower() or "Cannot connect" in out:
        return [{"error": "Docker not available on this server"}]
    return lines if lines else [{"info": "No Docker containers found"}]

@tool
def get_docker_stats(server_name: str = "local") -> list:
    """Get Docker container resource usage (CPU, memory).
    Use when asked: docker CPU usage, container memory, docker resource usage, container stats
    server_name: local, dev, or test
    """
    out = _run(server_name, "docker stats --no-stream --format 'table {{.Name}}\\t{{.CPUPerc}}\\t{{.MemUsage}}\\t{{.NetIO}}' 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if "command not found" in out.lower():
        return [{"error": "Docker not available"}]
    return lines if lines else [{"info": "No running containers"}]

@tool
def get_service_logs(server_name: str = "local", service: str = "nginx", lines: int = 50) -> list:
    """Get recent logs from a systemd service using journalctl.
    Use when asked: nginx logs, show service logs, journalctl for X, service log output
    server_name: local, dev, or test
    service: service name e.g. nginx, apache2, postgresql, docker
    lines: number of log lines (default 50)
    """
    out = _run(server_name, f"journalctl -u {service} --no-pager -n {lines} 2>/dev/null || systemctl status {service} 2>/dev/null | tail -{lines}")
    result = [l.strip() for l in out.splitlines() if l.strip()]
    return result if result else [f"No logs found for service: {service}"]

@tool
def get_environment_check(server_name: str = "local") -> dict:
    """Check critical environment variables and system configuration.
    Use when asked: environment check, system config, verify env vars, configuration audit
    server_name: local, dev, or test
    """
    out = _run(server_name, "ulimit -a 2>/dev/null | head -15 && echo '---' && cat /proc/sys/vm/swappiness 2>/dev/null && echo '---' && sysctl net.core.somaxconn 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return {"server": server_name, "system_limits": lines}

@tool
def check_disk_smart(server_name: str = "local") -> dict:
    """Check disk health using SMART data.
    Use when asked: disk health, SMART data, is disk failing, disk errors, hardware health
    server_name: local, dev, or test
    """
    out = _run(server_name, "smartctl -H /dev/sda 2>/dev/null || smartctl -H /dev/nvme0 2>/dev/null || echo 'SMART not available'")
    healthy = "PASSED" in out or "OK" in out
    return {
        "server": server_name,
        "healthy": healthy,
        "status": "PASSED" if healthy else "FAILED or unavailable",
        "raw": [l.strip() for l in out.splitlines() if l.strip()][:10],
    }

@tool
def get_swap_activity(server_name: str = "local") -> dict:
    """Get swap memory activity — detect memory thrashing.
    Use when asked: swap usage, is server swapping, memory thrashing, swap in out
    server_name: local, dev, or test
    """
    out = _run(server_name, "vmstat 1 3 2>/dev/null | tail -3 && free -h 2>/dev/null")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    vmstat_lines = [l for l in lines if l[0].isdigit()]
    swapping = False
    if vmstat_lines:
        parts = vmstat_lines[-1].split()
        if len(parts) >= 8:
            si = int(parts[6]) if parts[6].isdigit() else 0
            so = int(parts[7]) if parts[7].isdigit() else 0
            swapping = si > 0 or so > 0
    return {
        "server": server_name,
        "swapping": swapping,
        "status": "THRASHING - high swap activity" if swapping else "Normal - no swap activity",
        "vmstat": vmstat_lines,
        "interpretation": "Server is using swap memory heavily — RAM is insufficient" if swapping else "RAM is sufficient — no swapping detected"
    }
'''

# ============================================================
# 7. registry.py — updated with all new tools
# ============================================================
files["agent/tools/registry.py"] = '''from tools.system_tools import (
    get_cpu_stats, get_memory_stats, get_disk_usage,
    get_network_stats, get_top_processes, get_system_uptime,
    get_load_average, get_open_ports,
)
from tools.cron_tools import (
    get_cron_jobs, get_cron_logs, get_failed_crons,
    create_cron_job, delete_cron_job,
)
from tools.process_tools import (
    get_process_by_name, get_zombie_processes,
)
from tools.log_tools import (
    tail_log_file, search_log_pattern, get_auth_failures,
    get_error_summary, get_oom_events, get_kernel_messages,
    get_application_errors, get_log_volume_trend, get_segfault_events,
)
from tools.prometheus_tools import (
    query_prometheus_instant, query_prometheus_range,
    get_prometheus_alerts, get_cpu_trend, get_memory_trend,
    get_disk_io_rate, get_network_bandwidth, get_cpu_iowait,
    compare_server_metrics, get_prometheus_targets, get_metric_anomaly,
)
from tools.grafana_tools import (
    post_grafana_annotation, get_grafana_annotations,
    get_annotations_timeline, get_grafana_dashboard_list,
    get_grafana_health,
)
from tools.rca_tools import (
    get_rca_report, get_system_baseline,
)
from tools.security_tools import (
    get_failed_ssh_attempts, get_active_sessions, get_sudo_history,
    get_firewall_rules, get_ssl_cert_expiry, get_listening_services,
    get_recent_logins, get_world_writable_files, get_failed_services,
    get_service_status,
)
from tools.application_tools import (
    check_port_open, check_url_health, check_process_alive,
    get_docker_containers, get_docker_stats, get_service_logs,
    get_environment_check, check_disk_smart, get_swap_activity,
)
from tools.alert_rules_tools import (
    create_alert_rule, list_alert_rules, remove_alert_rule,
)
from tools.notification_tools import (
    send_slack_alert, send_email_alert,
)

TOOL_GROUPS: dict[str, list] = {
    "system": [
        get_cpu_stats, get_memory_stats, get_disk_usage,
        get_network_stats, get_top_processes, get_system_uptime,
        get_load_average, get_open_ports, get_swap_activity,
    ],
    "cron": [
        get_cron_jobs, get_cron_logs, get_failed_crons,
        create_cron_job, delete_cron_job,
    ],
    "process": [
        get_process_by_name, get_zombie_processes,
    ],
    "logs": [
        tail_log_file, search_log_pattern, get_auth_failures,
        get_error_summary, get_oom_events, get_kernel_messages,
        get_application_errors, get_log_volume_trend, get_segfault_events,
    ],
    "prometheus": [
        query_prometheus_instant, query_prometheus_range,
        get_prometheus_alerts, get_cpu_trend, get_memory_trend,
        get_disk_io_rate, get_network_bandwidth, get_cpu_iowait,
        compare_server_metrics, get_prometheus_targets, get_metric_anomaly,
    ],
    "grafana": [
        post_grafana_annotation, get_grafana_annotations,
        get_annotations_timeline, get_grafana_dashboard_list,
        get_grafana_health,
    ],
    "rca": [
        get_rca_report, get_system_baseline,
    ],
    "security": [
        get_failed_ssh_attempts, get_active_sessions, get_sudo_history,
        get_firewall_rules, get_ssl_cert_expiry, get_listening_services,
        get_recent_logins, get_world_writable_files, get_failed_services,
        get_service_status,
    ],
    "application": [
        check_port_open, check_url_health, check_process_alive,
        get_docker_containers, get_docker_stats, get_service_logs,
        get_environment_check, check_disk_smart,
    ],
    "alerts": [
        create_alert_rule, list_alert_rules, remove_alert_rule,
    ],
    "notification": [
        send_slack_alert, send_email_alert,
    ],
}

ALWAYS_ON: list = (
    TOOL_GROUPS["system"]
    + TOOL_GROUPS["notification"]
    + TOOL_GROUPS["alerts"]
)

def get_tools_for_intent(intents: list[str]) -> list:
    seen = set()
    tools = []
    for t in ALWAYS_ON:
        if t.name not in seen:
            tools.append(t)
            seen.add(t.name)
    for intent in intents:
        for t in TOOL_GROUPS.get(intent, []):
            if t.name not in seen:
                tools.append(t)
                seen.add(t.name)
    return tools

def get_all_tools() -> list:
    seen = set()
    tools = []
    for group in TOOL_GROUPS.values():
        for t in group:
            if t.name not in seen:
                tools.append(t)
                seen.add(t.name)
    return tools
'''

# ============================================================
# 8. classifier.py — add new intents
# ============================================================
files["agent/graph/nodes/classifier.py"] = '''import logging
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
'''

# Write all files
for path, content in files.items():
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    print(f"✓ {path}")

print("\n✅ All 70 tools files created")
print("\nTool count:")
print("  System:      9 tools")
print("  Cron:        5 tools")
print("  Process:     2 tools")
print("  Logs:        9 tools  (+6 new)")
print("  Prometheus: 11 tools  (+8 new)")
print("  Grafana:     5 tools  (+3 new)")
print("  RCA:         2 tools  (NEW)")
print("  Security:   10 tools  (NEW)")
print("  Application: 9 tools  (NEW)")
print("  Alerts:      3 tools")
print("  Notification:2 tools")
print("  TOTAL:      67 tools")