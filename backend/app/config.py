from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "workers/.env"),
        env_prefix="QUEME_",
        extra="ignore",
    )

    database_url: str = ""
    internal_api_token: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    bootstrap_secret: str = ""
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://localhost:8080"])
    database_connect_timeout_seconds: float = Field(default=2.0, ge=0.1, le=10.0)
    audio_job_max_attempts: int = Field(default=4, ge=1, le=10)
    audio_job_timeout_seconds: int = Field(default=300, ge=1, le=3600)
    audio_job_lease_seconds: int = Field(default=360, ge=2, le=7200)
    audio_worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=30.0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
