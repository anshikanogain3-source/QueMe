from urllib.parse import urlparse

import asyncpg

from .config import Settings


def connection_ssl(database_url: str) -> str | None:
    hostname = urlparse(database_url).hostname
    if hostname in {"localhost", "127.0.0.1", "postgres"}:
        return None
    return "require"


async def connect_database(settings: Settings) -> asyncpg.Connection:
    if not settings.database_url:
        raise RuntimeError("Database URL is not configured.")
    return await asyncpg.connect(
        settings.database_url,
        timeout=settings.database_connect_timeout_seconds,
        ssl=connection_ssl(settings.database_url),
    )
