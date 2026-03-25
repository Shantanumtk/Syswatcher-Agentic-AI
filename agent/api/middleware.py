import time
import logging
from fastapi import Request

logger = logging.getLogger("syswatcher.http")

async def log_requests(request: Request, call_next):
    start    = time.time()
    response = await call_next(request)
    ms       = round((time.time() - start) * 1000, 1)
    logger.info(
        f"{request.method} {request.url.path} "
        f"→ {response.status_code} ({ms}ms)"
    )
    return response
