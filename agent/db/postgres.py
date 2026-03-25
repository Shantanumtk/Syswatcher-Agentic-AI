import asyncpg
import logging
import os

logger = logging.getLogger("syswatcher.db")

_pool: asyncpg.Pool = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "syswatcher"),
            password=os.getenv("POSTGRES_PASSWORD", "syswatcher123"),
            database=os.getenv("POSTGRES_DB", "syswatcher"),
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        logger.info("Postgres connection pool created")
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Postgres connection pool closed")
