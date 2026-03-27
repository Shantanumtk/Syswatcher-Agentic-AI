#!/usr/bin/env python3
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [mcp] %(levelname)s - %(message)s")
logger = logging.getLogger("syswatcher.mcp")

API_URL = os.getenv("SYSWATCHER_API", "http://agent:8000")
API_KEY = os.getenv("MCP_API_KEY", "syswatcher123")

mcp = Server("syswatcher")

async def _call_api(method, path, body=None):
    async with httpx.AsyncClient(timeout=120) as client:
        if method == "GET":
            r = await client.get(f"{API_URL}{path}", params=body or {})
        elif method == "DELETE":
            r = await client.delete(f"{API_URL}{path}")
        else:
            r = await client.post(f"{API_URL}{path}", json=body or {})
        r.raise_for_status()
        return r.json()

def _text(data):
    if isinstance(data, (dict, list)):
        return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]
    return [TextContent(type="text", text=str(data))]

def _join(lines):
    return [TextContent(type="text", text="\n".join(lines))]

@mcp.list_tools()
async def list_tools():
    return [
        Tool(name="ask_syswatcher", description="Ask SysWatcher anything in plain English. Examples: is everything ok, what is CPU on dev, did crons fail on test", inputSchema={"type":"object","properties":{"question":{"type":"string"},"server_name":{"type":"string","default":"local"}},"required":["question"]}),
        Tool(name="run_sweep", description="Run a full health sweep on a server", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_server_status", description="Get quick health status of a server", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="list_servers", description="List all monitored servers", inputSchema={"type":"object","properties":{}}),
        Tool(name="get_alert_rules", description="List all alert rules", inputSchema={"type":"object","properties":{"server_name":{"type":"string"}}}),
        Tool(name="create_alert", description="Create a new alert rule", inputSchema={"type":"object","properties":{"metric":{"type":"string"},"condition":{"type":"string"},"threshold":{"type":"number"},"severity":{"type":"string"},"notify_slack":{"type":"boolean","default":True},"description":{"type":"string"}},"required":["metric","condition","threshold","severity"]}),
        Tool(name="delete_alert", description="Delete an alert rule by ID", inputSchema={"type":"object","properties":{"rule_id":{"type":"integer"}},"required":["rule_id"]}),
        Tool(name="get_recent_events", description="Get recent health events", inputSchema={"type":"object","properties":{"server_name":{"type":"string"},"severity":{"type":"string"},"limit":{"type":"integer","default":20}}}),
        Tool(name="get_sweep_history", description="Get sweep history", inputSchema={"type":"object","properties":{"server_name":{"type":"string"},"limit":{"type":"integer","default":10}}}),
        Tool(name="get_cpu_stats", description="Get CPU usage for a server", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_memory_stats", description="Get memory usage for a server", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="get_disk_usage", description="Get disk usage for a server", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"path":{"type":"string","default":"/"}}}),
        Tool(name="get_top_processes", description="Get top processes by CPU", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"},"limit":{"type":"integer","default":10}}}),
        Tool(name="get_cron_jobs", description="List cron jobs on a server", inputSchema={"type":"object","properties":{"server_name":{"type":"string","default":"local"}}}),
        Tool(name="create_cron_job", description="Create a cron job on a server", inputSchema={"type":"object","properties":{"name":{"type":"string"},"schedule":{"type":"string"},"command":{"type":"string"},"server_name":{"type":"string","default":"local"},"log_path":{"type":"string"}},"required":["name","schedule","command"]}),
    ]

@mcp.call_tool()
async def call_tool(name, arguments):
    logger.info(f"Tool called: {name} args={arguments}")
    try:
        if name == "ask_syswatcher":
            result = await _call_api("POST", "/ask", {"question": arguments["question"], "server_name": arguments.get("server_name", "local")})
            sev = result.get("severity", "healthy").upper()
            ans = result.get("answer", "")
            return [TextContent(type="text", text="[" + sev + "] " + ans)]

        elif name == "run_sweep":
            result = await _call_api("POST", "/sweep", {"server_name": arguments.get("server_name", "local")})
            sev = result.get("severity", "healthy").upper()
            rep = result.get("report", "")
            return [TextContent(type="text", text="[" + sev + "]\n\n" + rep)]

        elif name == "get_server_status":
            result = await _call_api("GET", "/status", {"server_name": arguments.get("server_name", "local"), "mins_back": 5})
            return _text(result)

        elif name == "list_servers":
            result = await _call_api("GET", "/servers")
            servers = result.get("servers", [])
            lines = ["- " + s["name"] + " | " + s["ip"] + " | user: " + str(s.get("ssh_user", "local")) for s in servers]
            return _join(lines) if lines else _text("No servers found")

        elif name == "get_alert_rules":
            params = {}
            if "server_name" in arguments:
                params["server_name"] = arguments["server_name"]
            result = await _call_api("GET", "/alerts", params)
            rules = result.get("rules", [])
            if not rules:
                return _text("No alert rules configured")
            lines = ["ID " + str(r["id"]) + ": " + r["metric"] + " " + r["condition"] + " " + str(r["threshold"]) + " -> " + r["severity"] + " slack=" + str(r["notify_slack"]) for r in rules]
            return _join(lines)

        elif name == "create_alert":
            result = await _call_api("POST", "/alerts", {"metric": arguments["metric"], "condition": arguments["condition"], "threshold": arguments["threshold"], "severity": arguments["severity"], "notify_slack": arguments.get("notify_slack", True), "description": arguments.get("description", "")})
            return _text(result)

        elif name == "delete_alert":
            result = await _call_api("DELETE", "/alerts/" + str(arguments["rule_id"]))
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
                return _text("No events found")
            lines = ["[" + e["severity"].upper() + "] " + str(e["timestamp"])[:19] + " " + e["server_name"] + " - " + e["message"] for e in events]
            return _join(lines)

        elif name == "get_sweep_history":
            params = {"limit": arguments.get("limit", 10)}
            if "server_name" in arguments:
                params["server_name"] = arguments["server_name"]
            result = await _call_api("GET", "/history/sweeps", params)
            sweeps = result.get("sweeps", [])
            if not sweeps:
                return _text("No sweeps found")
            lines = ["[" + s["overall"].upper() + "] " + str(s["started_at"])[:19] + " " + s["server_name"] for s in sweeps]
            return _join(lines)

        elif name == "get_cpu_stats":
            result = await _call_api("POST", "/ask", {"question": "what is the CPU usage?", "server_name": arguments.get("server_name", "local")})
            return _text(result.get("answer", ""))

        elif name == "get_memory_stats":
            result = await _call_api("POST", "/ask", {"question": "what is the memory usage?", "server_name": arguments.get("server_name", "local")})
            return _text(result.get("answer", ""))

        elif name == "get_disk_usage":
            result = await _call_api("POST", "/ask", {"question": "what is the disk usage on " + arguments.get("path", "/") + "?", "server_name": arguments.get("server_name", "local")})
            return _text(result.get("answer", ""))

        elif name == "get_top_processes":
            result = await _call_api("POST", "/ask", {"question": "what are the top " + str(arguments.get("limit", 10)) + " processes by CPU?", "server_name": arguments.get("server_name", "local")})
            return _text(result.get("answer", ""))

        elif name == "get_cron_jobs":
            result = await _call_api("POST", "/ask", {"question": "list all cron jobs", "server_name": arguments.get("server_name", "local")})
            return _text(result.get("answer", ""))

        elif name == "create_cron_job":
            q = "create a cron job called " + arguments["name"] + " that runs '" + arguments["command"] + "' on schedule '" + arguments["schedule"] + "'"
            if arguments.get("log_path"):
                q += " and logs to " + arguments["log_path"]
            result = await _call_api("POST", "/ask", {"question": q, "server_name": arguments.get("server_name", "local")})
            return _text(result.get("answer", ""))

        else:
            return _text("Unknown tool: " + name)

    except Exception as e:
        logger.error(f"Tool error: {e}", exc_info=True)
        return _text("Error: " + str(e))

sse = SseServerTransport("/messages/")

async def health(request):
    return JSONResponse({"status": "ok", "service": "syswatcher-mcp", "tools": 15})

async def handle_sse(request):
    key = request.headers.get("x-api-key", "")
    if API_KEY and key != API_KEY:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp.run(streams[0], streams[1], mcp.create_initialization_options())

async def handle_messages(request):
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
    logger.info("SysWatcher MCP Server starting on port 8080")
    logger.info("API: " + API_URL)
    uvicorn.run(app, host="0.0.0.0", port=8080)