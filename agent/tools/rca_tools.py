import os
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
