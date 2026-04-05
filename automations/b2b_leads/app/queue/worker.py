import os
import json
import logging
import asyncio
from typing import Callable, Any

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
QUEUE_NAME = "b2b_leads"


async def enqueue(task_name: str, payload: dict) -> None:
    """Добавить задачу в Redis-очередь."""
    try:
        import aioredis
        redis = await aioredis.from_url(REDIS_URL)
        await redis.lpush(QUEUE_NAME, json.dumps({"task": task_name, "payload": payload}))
        await redis.close()
        logger.info(f"Task enqueued: {task_name}")
    except ImportError:
        logger.warning("aioredis not installed. Running task directly.")
        await _run_direct(task_name, payload)
    except Exception as e:
        logger.error(f"Queue error: {e}. Running task directly.")
        await _run_direct(task_name, payload)


async def _run_direct(task_name: str, payload: dict) -> None:
    """Fallback: выполнить задачу напрямую без очереди."""
    if task_name == "process_lead":
        from app.main import process_lead
        await process_lead(payload)


async def start_worker() -> None:
    """Запустить воркер очереди (запускать отдельным процессом)."""
    try:
        import aioredis
        redis = await aioredis.from_url(REDIS_URL)
        logger.info(f"Worker started, listening on {QUEUE_NAME}")
        while True:
            _, raw = await redis.brpop(QUEUE_NAME, timeout=5) or (None, None)
            if raw:
                task_data = json.loads(raw)
                await _run_direct(task_data["task"], task_data["payload"])
            await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"Worker error: {e}")


if __name__ == "__main__":
    asyncio.run(start_worker())
