import os
import time
import logging
import httpx
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [scheduler] %(levelname)s — %(message)s",
)
logger = logging.getLogger("syswatcher.scheduler")

AGENT_URL      = os.getenv("AGENT_URL", "http://agent:8000")
SWEEP_INTERVAL = int(os.getenv("SWEEP_INTERVAL_MIN", "5"))
SERVERS_RAW    = os.getenv("SERVERS", "local")

def get_servers() -> list[str]:
    """
    Returns list of server names to sweep.
    Reads SERVERS env var — comma-separated names.
    Always includes 'local'.
    """
    names = [s.strip() for s in SERVERS_RAW.split(",") if s.strip()]
    if "local" not in names:
        names.insert(0, "local")
    return names

def wait_for_agent(max_wait: int = 120) -> bool:
    """Poll agent /health until ready or timeout."""
    logger.info(f"Waiting for agent at {AGENT_URL}...")
    waited = 0
    while waited < max_wait:
        try:
            r = httpx.get(f"{AGENT_URL}/health", timeout=5)
            if r.status_code == 200 and r.json().get("database") == "ok":
                logger.info("Agent is ready")
                return True
        except Exception:
            pass
        time.sleep(5)
        waited += 5
        logger.info(f"Still waiting for agent... ({waited}s)")
    logger.error("Agent did not become ready in time")
    return False

def run_sweep(server_name: str = "local"):
    """Call POST /sweep for a single server."""
    started = datetime.now()
    try:
        logger.info(f"Starting sweep — server={server_name}")
        r = httpx.post(
            f"{AGENT_URL}/sweep",
            json={"server_name": server_name},
            timeout=180,                    # sweeps can take a while
        )
        if r.status_code == 200:
            data     = r.json()
            severity = data.get("severity", "unknown")
            report   = data.get("report", "")[:120]
            elapsed  = round((datetime.now() - started).total_seconds(), 1)
            logger.info(
                f"Sweep done — server={server_name} "
                f"severity={severity} elapsed={elapsed}s"
            )
            logger.info(f"Summary: {report}")
        else:
            logger.error(
                f"Sweep failed — server={server_name} "
                f"status={r.status_code} body={r.text[:200]}"
            )
    except httpx.TimeoutException:
        logger.error(f"Sweep timed out — server={server_name}")
    except Exception as e:
        logger.error(f"Sweep error — server={server_name}: {e}")

def run_all_sweeps():
    """Sweep every configured server sequentially."""
    servers = get_servers()
    logger.info(f"Sweeping {len(servers)} server(s): {servers}")
    for server in servers:
        run_sweep(server)

def register_servers():
    """
    Register all configured servers in the agent DB.
    Reads SERVER_<NAME>_IP env vars set by generate_configs.py.
    """
    servers = get_servers()
    for name in servers:
        if name == "local":
            ip = "127.0.0.1"
        else:
            ip = os.getenv(f"SERVER_{name.upper().replace('-','_')}_IP", "")
        if not ip:
            continue
        try:
            r = httpx.post(
                f"{AGENT_URL}/servers",
                json={"name": name, "ip": ip},
                timeout=10,
            )
            if r.status_code == 200:
                logger.info(f"Server registered: {name} ({ip})")
        except Exception as e:
            logger.warning(f"Could not register server {name}: {e}")

def on_job_error(event):
    logger.error(f"Scheduled job crashed: {event.exception}")

def on_job_executed(event):
    logger.debug(f"Job executed: {event.job_id}")

if __name__ == "__main__":
    logger.info("SysWatcher scheduler starting...")
    logger.info(f"Sweep interval: every {SWEEP_INTERVAL} minute(s)")
    logger.info(f"Servers: {get_servers()}")

    # Wait for agent to be healthy before doing anything
    if not wait_for_agent():
        logger.error("Exiting — agent never became ready")
        exit(1)

    # Register servers in DB
    register_servers()

    # Run first sweep immediately on startup
    logger.info("Running initial sweep...")
    run_all_sweeps()

    # Schedule recurring sweeps
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_listener(on_job_error, EVENT_JOB_ERROR)
    scheduler.add_listener(on_job_executed, EVENT_JOB_EXECUTED)

    scheduler.add_job(
        run_all_sweeps,
        trigger="interval",
        minutes=SWEEP_INTERVAL,
        id="sweep_all",
        name="Sweep all servers",
        max_instances=1,            # never run two sweeps in parallel
        coalesce=True,              # skip missed runs if behind
    )

    logger.info(
        f"Scheduler started — next sweep in {SWEEP_INTERVAL} minute(s)"
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
