import hmac
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..config import Settings, get_settings
from ..database import connect_database
from ..request_context import current_request_id
from ..schemas import AudioJobAccepted, AudioJobSubmission

router = APIRouter(prefix="/audio-jobs", tags=["audio jobs"])


@router.post("", response_model=AudioJobAccepted, status_code=202)
async def submit_audio_job(
    submission: AudioJobSubmission,
    request: Request,
    x_internal_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> AudioJobAccepted:
    if not settings.internal_api_token:
        raise HTTPException(status_code=503, detail="Internal job submission is not configured.")
    if not x_internal_token or not hmac.compare_digest(x_internal_token, settings.internal_api_token):
        raise HTTPException(status_code=401, detail="A valid internal service token is required.")

    payload = {
        "session_id": str(submission.session_id),
        "storage_object_path": submission.storage_object_path,
    }
    request_id = current_request_id()
    connection = None
    try:
        connection = await connect_database(settings)
        row = await connection.fetchrow(
            """
            INSERT INTO public.audio_analysis_jobs
                (job_type, idempotency_key, payload, request_id, max_attempts)
            VALUES ('audio_analysis', $1, $2::jsonb, $3::uuid, $4)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, status, attempt_count, max_attempts, payload
            """,
            submission.idempotency_key,
            json.dumps(payload),
            request_id,
            settings.audio_job_max_attempts,
        )
        if row is None:
            row = await connection.fetchrow(
                "SELECT id, status, attempt_count, max_attempts, payload FROM public.audio_analysis_jobs WHERE idempotency_key = $1",
                submission.idempotency_key,
            )
            if row is None:
                raise HTTPException(status_code=503, detail="The job could not be stored.")
            stored_payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
            if stored_payload != payload:
                raise HTTPException(status_code=409, detail="Idempotency key was already used for a different job payload.")
    except HTTPException:
        raise
    except Exception as exc:
        request.app.logger.warning("audio job persistence failed request_id=%s error_type=%s", request_id, type(exc).__name__)
        raise HTTPException(status_code=503, detail="The job service is temporarily unavailable.") from exc
    finally:
        if connection is not None:
            await connection.close()

    return AudioJobAccepted(
        id=UUID(str(row["id"])),
        status=row["status"],
        attempt_count=row["attempt_count"],
        max_attempts=row["max_attempts"],
        request_id=request_id,
    )
