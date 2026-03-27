import os

files = {}

# ============================================================
# 1. mcp/requirements.txt
# ============================================================
files["mcp/requirements.txt"] = """mcp[cli]==1.6.0
httpx==0.27.0
starlette==0.37.2
uvicorn[standard]==0.29.0
python-dotenv==1.0.1
"""

# ============================================================
# 2. mcp/Dockerfile
# ============================================================
files["mcp/Dockerfile"] = """FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "-u", "mcp_server.py"]
"""

# ============================================================
# 3. mcp/mcp_server.py
# ============================================================
files["mcp/mcp_server.py"] = '''#!/usr/bin/env python3
"""
SysWatcher MCP Server
Exposes all SysWatcher tools as MCP tools via HTTP SSE transport.
Runs on jump server port 8080.
"""
import os
import json
import logging
import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request
from starlette.responses import JSONResponse
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [mcp] %(levelname)s — %(message)s")
logger = logging.getLogger("syswatcher.mcp")

API_URL = os.getenv("SYSWATCHER_API", "http://agent:8000")
API_KEY = os.getenv("MCP_API_KEY", "syswatcher123")

# ── MCP Server ────────────────────────────────────────────────
mcp = Server("syswatcher")

# ── Helper ───────────────────────────────────────────────────
async def _call_api(method: str, path: str, body: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=120) as client:
        if method == "GET":
            r = await client.get(f"{API_URL}{path}", params=body or {})
        else:
            r = await client.post(f"{API_URL}{path}", json=body or {})
        r.raise_for_status()
        return r.json()

def _text(data) -> list[TextContent]:
    if isinstance(data, (dict, list)):
        return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]
    return [TextContent(type="text", text=str(data))]

# ── Tool definitions ──────────────────────────────────────────
@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="ask_syswatcher",
            description="Ask SysWatcher anything about your servers in plain English. The AI agent collects live data and answers. Examples: 'is everything ok?', 'what is CPU usage on dev?', 'did any crons fail?', 'show disk usage on test server'",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Your question in plain English"},
                    "server_name": {"type": "string", "description": "Server to query: local, dev, or test (default: local)", "default": "local"},
                },
                "required": ["question"],
            },
        ),
        Tool(
            name="run_sweep",
            description="Run a full health sweep on a server — checks CPU, memory, disk, network, crons, Prometheus alerts and returns a complete health report",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "Server to sweep: local, dev, or test (default: local)", "default": "local"},
                },
            },
        ),
        Tool(
            name="get_server_status",
            description="Get quick health status of a server — overall health, critical/warn event counts, last sweep time",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "Server name: local, dev, or test", "default": "local"},
                },
            },
        ),
        Tool(
            name="list_servers",
            description="List all servers being monitored by SysWatcher with their IPs and status",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_alert_rules",
            description="List all configured alert rules — metric thresholds that trigger Slack notifications",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "Filter by server name (optional)"},
                },
            },
        ),
        Tool(
            name="create_alert",
            description="Create a new alert rule — triggers Slack notification when metric crosses threshold",
            inputSchema={
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "description": "Metric to monitor: cpu_usage_pct, memory_usage_pct, disk_usage_pct, load_avg_1m"},
                    "condition": {"type": "string", "description": "Condition: gt (greater than), lt (less than), eq (equal)"},
                    "threshold": {"type": "number", "description": "Threshold value e.g. 80.0"},
                    "severity": {"type": "string", "description": "Severity: warn or critical"},
                    "notify_slack": {"type": "boolean", "description": "Send Slack notification when triggered", "default": True},
                    "description": {"type": "string", "description": "Human readable description"},
                },
                "required": ["metric", "condition", "threshold", "severity"],
            },
        ),
        Tool(
            name="delete_alert",
            description="Delete an alert rule by its ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_id": {"type": "integer", "description": "Alert rule ID from get_alert_rules"},
                },
                "required": ["rule_id"],
            },
        ),
        Tool(
            name="get_recent_events",
            description="Get recent health events — critical alerts, warnings, and info events stored during sweeps",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "Filter by server name (optional)"},
                    "severity": {"type": "string", "description": "Filter by severity: info, warn, or critical (optional)"},
                    "limit": {"type": "integer", "description": "Max results (default: 20)", "default": 20},
                },
            },
        ),
        Tool(
            name="get_sweep_history",
            description="Get history of recent health sweeps — timestamps, severity, and summaries",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "Filter by server name (optional)"},
                    "limit": {"type": "integer", "description": "Max results (default: 10)", "default": 10},
                },
            },
        ),
        Tool(
            name="get_cpu_stats",
            description="Get live CPU usage, per-core breakdown and load average for a server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "Server: local, dev, or test", "default": "local"},
                },
            },
        ),
        Tool(
            name="get_memory_stats",
            description="Get live RAM and swap usage for a server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "Server: local, dev, or test", "default": "local"},
                },
            },
        ),
        Tool(
            name="get_disk_usage",
            description="Get live disk usage for a server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "Server: local, dev, or test", "default": "local"},
                    "path": {"type": "string", "description": "Mount point (default: /)", "default": "/"},
                },
            },
        ),
        Tool(
            name="get_top_processes",
            description="Get top processes by CPU usage on a server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "Server: local, dev, or test", "default": "local"},
                    "limit": {"type": "integer", "description": "Number of processes (default: 10)", "default": 10},
                },
            },
        ),
        Tool(
            name="get_cron_jobs",
            description="List all cron jobs on a server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "Server: local, dev, or test", "default": "local"},
                },
            },
        ),
        Tool(
            name="create_cron_job",
            description="Create a new cron job on a server",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Friendly name e.g. daily_backup"},
                    "schedule": {"type": "string", "description": "Cron expression e.g. '0 2 * * *' for 2am daily"},
                    "command": {"type": "string", "description": "Command to run e.g. /opt/scripts/backup.sh"},
                    "server_name": {"type": "string", "description": "Server: local, dev, or test", "default": "local"},
                    "log_path": {"type": "string", "description": "Log file path (optional)"},
                },
                "required": ["name", "schedule", "command"],
            },
        ),
    ]

# ── Tool handlers ─────────────────────────────────────────────
@mcp.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    logger.info(f"Tool called: {name} args={arguments}")
    try:
        if name == "ask_syswatcher":
            result = await _call_api("POST", "/ask", {
                "question": arguments["question"],
                "server_name": arguments.get("server_name", "local"),
            })
            answer = result.get("answer", "")
            severity = result.get("severity", "healthy")
            return [TextContent(type="text", text=f"[{severity.upper()}] {answer}")]

        elif name == "run_sweep":
            result = await _call_api("POST", "/sweep", {
                "server_name": arguments.get("server_name", "local"),
            })
            report = result.get("report", "")
            severity = result.get("severity", "healthy")
            return [TextContent(type="text", text=f"[{severity.upper()}]\n\n{report}")]

        elif name == "get_server_status":
            result = await _call_api("GET", "/status", {
                "server_name": arguments.get("server_name", "local"),
                "mins_back": 5,
            })
            return _text(result)

        elif name == "list_servers":
            result = await _call_api("GET", "/servers")
            servers = result.get("servers", [])
            lines = [f"• {s['name']} — {s['ip']} (user: {s.get('ssh_user','local')})" for s in servers]
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "get_alert_rules":
            params = {}
            if "server_name" in arguments:
                params["server_name"] = arguments["server_name"]
            result = await _call_api("GET", "/alerts", params)
            rules = result.get("rules", [])
            lines = [f"ID {r['id']}: {r['metric']} {r['condition']} {r['threshold']} → {r['severity']} (slack={r['notify_slack']})" for r in rules]
            return [TextContent(type="text", text="\n".join(lines) if lines else "No alert rules configured")]

        elif name == "create_alert":
            result = await _call_api("POST", "/alerts", {
                "metric": arguments["metric"],
                "condition": arguments["condition"],
                "threshold": arguments["threshold"],
                "severity": arguments["severity"],
                "notify_slack": arguments.get("notify_slack", True),
                "description": arguments.get("description", ""),
            })
            return _text(result)

        elif name == "delete_alert":
            result = await _call_api("DELETE" , f"/alerts/{arguments['rule_id']}")
            return _text(result)

        elif name == "get_recent_events":
            params = {"limit": arguments.get("limit", 20)}
            if "server_name" in arguments:
                params["server_name"] = arguments["server_name"]
            if "severity" in arguments:
                params["severity"] = arguments["severity"]
            result = await _call_api("GET", "/history/events", params)
            events = result.get("events", [])
            if not events:
                return [TextContent(type="text", text="No events found")]
            lines = [f"[{e['severity'].upper()}] {e['timestamp'][:19]} {e['server_name']} — {e['message']}" for e in events]
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "get_sweep_history":
            params = {"limit": arguments.get("limit", 10)}
            if "server_name" in arguments:
                params["server_name"] = arguments["server_name"]
            result = await _call_api("GET", "/history/sweeps", params)
            sweeps = result.get("sweeps", [])
            if not sweeps:
                return [TextContent(type="text", text="No sweeps found")]
            lines = [f"[{s['overall'].upper()}] {str(s['started_at'])[:19]} {s['server_name']} — {(s.get('summary') or '')[:80]}" for s in sweeps]
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "get_cpu_stats":
            result = await _call_api("POST", "/ask", {
                "question": "what is the CPU usage?",
                "server_name": arguments.get("server_name", "local"),
            })
            return [TextContent(type="text", text=result.get("answer", ""))]

        elif name == "get_memory_stats":
            result = await _call_api("POST", "/ask", {
                "question": "what is the memory usage?",
                "server_name": arguments.get("server_name", "local"),
            })
            return [TextContent(type="text", text=result.get("answer", ""))]

        elif name == "get_disk_usage":
            result = await _call_api("POST", "/ask", {
                "question": f"what is the disk usage on {arguments.get('path', '/')}?",
                "server_name": arguments.get("server_name", "local"),
            })
            return [TextContent(type="text", text=result.get("answer", ""))]

        elif name == "get_top_processes":
            result = await _call_api("POST", "/ask", {
                "question": f"what are the top {arguments.get('limit', 10)} processes by CPU?",
                "server_name": arguments.get("server_name", "local"),
            })
            return [TextContent(type="text", text=result.get("answer", ""))]

        elif name == "get_cron_jobs":
            result = await _call_api("POST", "/ask", {
                "question": "list all cron jobs",
                "server_name": arguments.get("server_name", "local"),
            })
            return [TextContent(type="text", text=result.get("answer", ""))]

        elif name == "create_cron_job":
            result = await _call_api("POST", "/ask", {
                "question": (
                    f"create a cron job called {arguments['name']} "
                    f"that runs '{arguments['command']}' "
                    f"on schedule '{arguments['schedule']}'"
                    + (f" and logs to {arguments['log_path']}" if arguments.get("log_path") else "")
                ),
                "server_name": arguments.get("server_name", "local"),
            })
            return [TextContent(type="text", text=result.get("answer", ""))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except httpx.HTTPError as e:
        return [TextContent(type="text", text=f"API error: {e}")]
    except Exception as e:
        logger.error(f"Tool error: {e}", exc_info=True)
        return [TextContent(type="text", text=f"Error: {e}")]

# ── Starlette app with API key auth ──────────────────────────
sse = SseServerTransport("/messages/")

async def health(request: Request):
    return JSONResponse({"status": "ok", "service": "syswatcher-mcp", "tools": 15})

async def handle_sse(request: Request):
    key = request.headers.get("x-api-key", "")
    if API_KEY and key != API_KEY:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp.run(streams[0], streams[1], mcp.create_initialization_options())

async def handle_messages(request: Request):
    key = request.headers.get("x-api-key", "")
    if API_KEY and key != API_KEY:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    await sse.handle_post_message(request.scope, request.receive, request._send)

app = Starlette(routes=[
    Route("/health", health),
    Route("/sse", handle_sse),
    Mount("/messages/", routes=[Route("/{path:path}", handle_messages, methods=["POST"])]),
])

if __name__ == "__main__":
    logger.info(f"SysWatcher MCP Server starting on port 8080")
    logger.info(f"SysWatcher API: {API_URL}")
    logger.info(f"API key auth: {'enabled' if API_KEY else 'disabled'}")
    uvicorn.run(app, host="0.0.0.0", port=8080)
'''

# ============================================================
# 4. docker-compose.yml update — add mcp service
# ============================================================
files["docker-compose.patch"] = """ADD_MCP_SERVICE"""

# ============================================================
# 5. Mac config files (instructions only — written as strings)
# ============================================================
files["mac_configs/cursor_mcp.json"] = '''{
  "mcpServers": {
    "syswatcher": {
      "url": "http://18.206.108.14:8080/sse",
      "headers": {
        "x-api-key": "syswatcher123"
      }
    }
  }
}
'''

files["mac_configs/claude_desktop_config.json"] = '''{
  "mcpServers": {
    "syswatcher": {
      "url": "http://18.206.108.14:8080/sse",
      "headers": {
        "x-api-key": "syswatcher123"
      }
    }
  }
}
'''

# Write all files
for path, content in files.items():
    if path == "docker-compose.patch":
        continue
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    print(f"✓ {path}")

# Patch docker-compose.yml
dc_path = "docker-compose.yml"
if os.path.exists(dc_path):
    with open(dc_path) as f:
        content = f.read()

    mcp_service = """
  mcp:
    build:
      context: ./mcp
      dockerfile: Dockerfile
    container_name: syswatcher-mcp
    restart: unless-stopped
    environment:
      - SYSWATCHER_API=http://agent:8000
      - MCP_API_KEY=${MCP_API_KEY:-syswatcher123}
    ports:
      - "8080:8080"
    depends_on:
      agent:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 10s
      timeout: 5s
      retries: 5
"""

    if "syswatcher-mcp" not in content:
        content = content.replace(
            "\nvolumes:",
            mcp_service + "\nvolumes:"
        )
        with open(dc_path, "w") as f:
            f.write(content)
        print("✓ docker-compose.yml updated with mcp service")
    else:
        print("✓ docker-compose.yml already has mcp service")
else:
    print("✗ docker-compose.yml not found — run from project root")

print("\n✅ All MCP files created")