import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from agent.db.postgres import get_pool, close_pool
from agent.api.middleware import log_requests
from agent.api.routes import ask, sweep, status, history, servers, alerts, crons

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("syswatcher")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to Postgres...")
    await get_pool()
    logger.info("Postgres ready — SysWatcher agent started")
    yield
    await close_pool()
    logger.info("Shutdown complete")

app = FastAPI(
    title="SysWatcher Agent",
    description="AI-powered server health monitoring agent",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(BaseHTTPMiddleware, dispatch=log_requests)

# ── Routes ────────────────────────────────────────
app.include_router(ask.router,     prefix="/ask",     tags=["Chat"])
app.include_router(sweep.router,   prefix="/sweep",   tags=["Sweep"])
app.include_router(status.router,  prefix="/status",  tags=["Status"])
app.include_router(history.router, prefix="/history", tags=["History"])
app.include_router(servers.router, prefix="/servers", tags=["Servers"])
app.include_router(alerts.router,  prefix="/alerts",  tags=["Alerts"])
app.include_router(crons.router,   prefix="/crons",   tags=["Crons"])

# ── Health ────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db = "ok"
    except Exception as e:
        db = f"error: {e}"
    return {"status": "ok", "service": "syswatcher-agent", "database": db}

@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "SysWatcher Agent",
        "docs":    "/docs",
        "health":  "/health",
        "routes": [
            "POST /ask",
            "POST /sweep",
            "GET  /status",
            "GET  /history/events",
            "GET  /history/sweeps",
            "GET  /history/summary",
            "GET  /servers",
            "POST /servers",
            "GET  /servers/{name}/summary",
            "GET  /alerts",
            "POST /alerts",
            "DEL  /alerts/{id}",
            "GET  /crons",
            "POST /crons",
            "DEL  /crons/{server}/{name}",
        ],
    }
