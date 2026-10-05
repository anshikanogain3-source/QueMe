from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import os
from collections.abc import Awaitable, Callable

import asyncpg

from backend.app.config import get_settings
from .queue import ClaimedJob, claim_job, mark_failed, mark_succeeded

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("queme.audio_worker")
Processor = Callable[[dict, str], Awaitable[dict]]


def load_processor() -> Processor:
    target = os.getenv("QUEME_AUDIO_PROCESSOR", "").strip()
    if not target or ":" not in target:
        raise RuntimeError("QUEME_AUDIO_PROCESSOR must point to a verified module:function adapter; no audio model is configured.")
    module_name, function_name = target.split(":", 1)
    processor = getattr(importlib.import_module(module_name), function_name, None)
    if not callable(processor):
        raise RuntimeError("Configured audio processor is not callable.")
    if not inspect.iscoroutinefunction(processor):
        raise RuntimeError("Configured audio processor must be async so the worker timeout can be enforced.")
    return processor


async def run_job(pool: asyncpg.Pool, job: ClaimedJob, processor: Processor, timeout_seconds: int) -> None:
    try:
        result = await asyncio.wait_for(
            processor(job.payload, job.idempotency_key),
            timeout=timeout_seconds,
        )
        if not isinstance(result, dict):
            raise TypeError("Audio processor must return a structured object.")
        await mark_succeeded(pool, job, result)
    except Exception as error:
        await mark_failed(pool, job, error)
        logger.warning(
            "audio job failed job_id=%s attempt=%s error_type=%s",
            job.id,
            job.attempt_count,
            type(error).__name__,
        )


async def run_worker() -> None:
    settings = get_settings()
    if settings.audio_job_lease_seconds <= settings.audio_job_timeout_seconds:
        raise RuntimeError("Audio job lease must exceed the processor timeout to avoid duplicate concurrent processing.")
    processor = load_processor()
    if not settings.database_url:
        raise RuntimeError("QUEME_DATABASE_URL is required to start the audio worker.")

    pool = await asyncpg.create_pool(settings.database_url)
    try:
        logger.info("audio worker started; processor=%s", os.getenv("QUEME_AUDIO_PROCESSOR"))
        while True:
            job = await claim_job(pool, settings.audio_job_lease_seconds)
            if job is None:
                await asyncio.sleep(settings.audio_worker_poll_seconds)
                continue
            await run_job(pool, job, processor, settings.audio_job_timeout_seconds)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run_worker())
