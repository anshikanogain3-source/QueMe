from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import asyncpg

from .retry_policy import retry_delay_seconds


@dataclass(frozen=True)
class ClaimedJob:
    id: UUID
    idempotency_key: str
    payload: dict
    attempt_count: int
    max_attempts: int
    locked_by: UUID


async def claim_job(pool: asyncpg.Pool, lease_seconds: int) -> ClaimedJob | None:
    worker_token = uuid4()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """
                UPDATE public.audio_analysis_jobs
                SET status = CASE WHEN attempt_count >= max_attempts THEN 'failed' ELSE 'retrying' END,
                    available_at = CASE WHEN attempt_count >= max_attempts THEN available_at ELSE now() END,
                    locked_by = NULL,
                    lease_expires_at = NULL,
                    last_error = 'Worker lease expired before job completion',
                    updated_at = now()
                WHERE status = 'processing' AND lease_expires_at < now()
                """
            )
            row = await connection.fetchrow(
                """
                SELECT id, idempotency_key, payload, attempt_count, max_attempts
                FROM public.audio_analysis_jobs
                WHERE status IN ('queued', 'retrying')
                  AND available_at <= now()
                  AND attempt_count < max_attempts
                ORDER BY available_at, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
            if row is None:
                return None

            updated = await connection.fetchrow(
                """
                UPDATE public.audio_analysis_jobs
                SET status = 'processing',
                    attempt_count = attempt_count + 1,
                    locked_by = $2,
                    lease_expires_at = now() + ($3 * interval '1 second'),
                    updated_at = now()
                WHERE id = $1
                RETURNING id, idempotency_key, payload, attempt_count, max_attempts
                """,
                row["id"], worker_token, lease_seconds,
            )
            payload = updated["payload"] if isinstance(updated["payload"], dict) else json.loads(updated["payload"])
            return ClaimedJob(
                id=updated["id"],
                idempotency_key=updated["idempotency_key"],
                payload=payload,
                attempt_count=updated["attempt_count"],
                max_attempts=updated["max_attempts"],
                locked_by=worker_token,
            )


async def mark_succeeded(pool: asyncpg.Pool, job: ClaimedJob, result: dict) -> None:
    async with pool.acquire() as connection:
        status = await connection.execute(
            """
            UPDATE public.audio_analysis_jobs
            SET status = 'succeeded', result = $3::jsonb, completed_at = now(),
                locked_by = NULL, lease_expires_at = NULL, updated_at = now()
            WHERE id = $1 AND locked_by = $2 AND status = 'processing'
            """,
            job.id, job.locked_by, json.dumps(result),
        )
    if status != "UPDATE 1":
        raise RuntimeError("Job lease was lost before success could be recorded.")


async def mark_failed(pool: asyncpg.Pool, job: ClaimedJob, error: Exception) -> None:
    retry = job.attempt_count < job.max_attempts
    delay = retry_delay_seconds(job.attempt_count) if retry else 0
    next_status = "retrying" if retry else "failed"
    safe_error = type(error).__name__[:120]
    async with pool.acquire() as connection:
        status = await connection.execute(
            """
            UPDATE public.audio_analysis_jobs
            SET status = $3,
                available_at = CASE WHEN $4 THEN now() + ($5 * interval '1 second') ELSE available_at END,
                last_error = $6,
                locked_by = NULL,
                lease_expires_at = NULL,
                completed_at = CASE WHEN $4 THEN NULL ELSE now() END,
                updated_at = now()
            WHERE id = $1 AND locked_by = $2 AND status = 'processing'
            """,
            job.id, job.locked_by, next_status, retry, delay, safe_error,
        )
    if status != "UPDATE 1":
        raise RuntimeError("Job lease was lost before failure could be recorded.")
