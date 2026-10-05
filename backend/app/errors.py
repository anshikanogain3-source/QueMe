from typing import Any
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .request_context import current_request_id

logger = logging.getLogger("queme.api")


def error_payload(code: str, message: str, details: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": current_request_id(),
    }
    if details:
        error["details"] = details
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in issue["loc"] if part != "body"),
                "message": issue["msg"],
            }
            for issue in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_payload("validation_error", "Request validation failed.", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_by_status = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            503: "service_not_configured",
        }
        message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code_by_status.get(exc.status_code, "internal_error"), message),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled request error request_id=%s", current_request_id())
        return JSONResponse(
            status_code=500,
            content=error_payload("internal_error", "An unexpected server error occurred."),
        )
