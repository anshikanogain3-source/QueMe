from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.health import router as health_router
from .api.jobs import router as jobs_router
from .api.recordings import router as recordings_router
from .api.admin import router as admin_router
from .api.admin_manage import router as admin_manage_router
from .config import get_settings
from .errors import register_error_handlers
from .request_context import RequestIdMiddleware

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.logger = logging.getLogger("queme.api")
    yield


settings = get_settings()
app = FastAPI(title="QueMe API", version="0.1.0", lifespan=lifespan)
app.logger = logging.getLogger("queme.api")
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Internal-Token", "X-Bootstrap-Secret"],
    expose_headers=["X-Request-ID"],
)
register_error_handlers(app)
app.include_router(health_router)
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(recordings_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(admin_manage_router, prefix="/api/v1")
