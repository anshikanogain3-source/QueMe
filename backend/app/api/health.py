from fastapi import APIRouter, HTTPException, Request

from ..config import get_settings
from ..database import connect_database
from ..request_context import current_request_id

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "request_id": current_request_id()}


@router.get("/ready")
async def readiness(request: Request) -> dict[str, object]:
    settings = get_settings()
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Database is not configured.")

    try:
        connection = await connect_database(settings)
        try:
            await connection.fetchval("SELECT 1")
        finally:
            await connection.close()
    except Exception as exc:
        request.app.logger.warning("readiness check failed request_id=%s error_type=%s", current_request_id(), type(exc).__name__)
        raise HTTPException(status_code=503, detail="Database readiness check failed.") from exc

    return {
        "status": "ready",
        "checks": {"database": "ok"},
        "request_id": current_request_id(),
    }
