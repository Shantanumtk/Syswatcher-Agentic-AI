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
