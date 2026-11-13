import math
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")


def _positive_int_env(name, default):
    try:
        value = int(os.getenv(name, default))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer.")
    return value


def _score_threshold_env(name, default):
    try:
        value = float(os.getenv(name, default))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number from 0 to 10.") from exc
    if not math.isfinite(value) or not 0 <= value <= 10:
        raise RuntimeError(f"{name} must be a number from 0 to 10.")
    return value


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{Path(__file__).resolve().parent / 'queme.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    LOG_DIR = Path(os.getenv("LOG_DIR", Path(__file__).resolve().parent / "logs"))
    if not LOG_DIR.is_absolute():
        LOG_DIR = Path(__file__).resolve().parent / LOG_DIR
    LOG_MAX_BYTES = _positive_int_env("LOG_MAX_BYTES", str(10 * 1024 * 1024))
    LOG_BACKUP_COUNT = _positive_int_env("LOG_BACKUP_COUNT", "5")

    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b").strip()
    OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip()
    OLLAMA_TIMEOUT = _positive_int_env("OLLAMA_TIMEOUT", "300")
    OLLAMA_LOCK_WAIT_TIMEOUT = _positive_int_env("OLLAMA_LOCK_WAIT_TIMEOUT", "30")
    OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
    OLLAMA_NUM_CTX = _positive_int_env("OLLAMA_NUM_CTX", "4096")
    OLLAMA_EVALUATION_BUDGET_SECONDS = _positive_int_env(
        "OLLAMA_EVALUATION_BUDGET_SECONDS", "600"
    )
    OLLAMA_EVALUATION_MIN_TOKENS = _positive_int_env(
        "OLLAMA_EVALUATION_MIN_TOKENS", "700"
    )
    OLLAMA_EVALUATION_MAX_TOKENS = _positive_int_env(
        "OLLAMA_EVALUATION_MAX_TOKENS", "1800"
    )
    ADAPTIVE_STRONG_THRESHOLD = _score_threshold_env("ADAPTIVE_STRONG_THRESHOLD", "8")
    ADAPTIVE_WEAK_THRESHOLD = _score_threshold_env("ADAPTIVE_WEAK_THRESHOLD", "5")
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
    STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").lower()
    STORAGE_LOCAL_DIR = Path(os.getenv("STORAGE_LOCAL_DIR", "uploads"))
    if not STORAGE_LOCAL_DIR.is_absolute():
        STORAGE_LOCAL_DIR = Path(__file__).resolve().parent / STORAGE_LOCAL_DIR
    R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "via-interview-audio")
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "").strip()
    S3_REGION = os.getenv("S3_REGION", os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))).strip()
    S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "").strip()
    S3_ADDRESSING_STYLE = os.getenv("S3_ADDRESSING_STYLE", "auto").strip().lower()
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
    ADMIN_FULL_NAME = os.getenv("ADMIN_FULL_NAME", "QueMe Administrator").strip()
    FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = _positive_int_env("SMTP_PORT", "587")
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "")
    SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
    JWT_EXP_HOURS = _positive_int_env("JWT_EXP_HOURS", "24")
    CONTENT_WEIGHT = 0.70
    DELIVERY_WEIGHT = 0.30


def validate_config(app):
    """Fail fast on deployment-critical configuration mistakes."""
    secret = app.config.get("SECRET_KEY")
    if not isinstance(secret, str) or len(secret) < 32 or "replace-with" in secret.lower():
        raise RuntimeError("Set SECRET_KEY to a randomly generated value of at least 32 characters in .env.")

    database_url = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not database_url:
        raise RuntimeError("Set DATABASE_URL to a local SQLite file or PostgreSQL connection URL in .env.")
    try:
        parsed_database_url = make_url(database_url)
    except Exception as exc:
        raise RuntimeError("DATABASE_URL is not a valid SQLite or PostgreSQL URL.") from exc
    if parsed_database_url.drivername.startswith("sqlite"):
        if not app.config.get("TESTING") and not parsed_database_url.database:
            raise RuntimeError("Use a SQLite file path in DATABASE_URL; in-memory SQLite is only for tests.")
    elif parsed_database_url.drivername in ("postgresql", "postgresql+psycopg2"):
        if not parsed_database_url.database or "change_me" in database_url.lower():
            raise RuntimeError("Set DATABASE_URL to a PostgreSQL URL with a real database name and credentials.")
    else:
        raise RuntimeError("DATABASE_URL must use SQLite (sqlite:///) or PostgreSQL.")

    if app.config.get("STORAGE_BACKEND") not in ("local", "r2", "s3"):
        raise RuntimeError("STORAGE_BACKEND must be 'local', 'r2', or 's3'.")
    app.config.setdefault("OLLAMA_EVALUATION_BUDGET_SECONDS", 600)
    app.config.setdefault("OLLAMA_LOCK_WAIT_TIMEOUT", 30)
    app.config.setdefault("OLLAMA_EVALUATION_MIN_TOKENS", 700)
    app.config.setdefault("OLLAMA_EVALUATION_MAX_TOKENS", 1800)
    app.config.setdefault("OLLAMA_NUM_CTX", 4096)
    for setting in (
        "OLLAMA_LOCK_WAIT_TIMEOUT", "OLLAMA_EVALUATION_BUDGET_SECONDS",
        "OLLAMA_EVALUATION_MIN_TOKENS", "OLLAMA_EVALUATION_MAX_TOKENS", "OLLAMA_NUM_CTX",
    ):
        try:
            app.config[setting] = int(app.config[setting])
        except (TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError(f"{setting} must be a positive integer.") from exc
        if app.config[setting] <= 0:
            raise RuntimeError(f"{setting} must be a positive integer.")
    if app.config["OLLAMA_EVALUATION_MAX_TOKENS"] < app.config["OLLAMA_EVALUATION_MIN_TOKENS"]:
        raise RuntimeError("OLLAMA_EVALUATION_MAX_TOKENS must be at least OLLAMA_EVALUATION_MIN_TOKENS.")
    if app.config["OLLAMA_EVALUATION_MAX_TOKENS"] > app.config["OLLAMA_NUM_CTX"]:
        raise RuntimeError("OLLAMA_EVALUATION_MAX_TOKENS cannot exceed OLLAMA_NUM_CTX.")
    strong_threshold = app.config.setdefault("ADAPTIVE_STRONG_THRESHOLD", 8.0)
    weak_threshold = app.config.setdefault("ADAPTIVE_WEAK_THRESHOLD", 5.0)
    try:
        thresholds_valid = (
            math.isfinite(float(strong_threshold))
            and math.isfinite(float(weak_threshold))
            and 0 <= float(weak_threshold) < float(strong_threshold) <= 10
        )
    except (TypeError, ValueError, OverflowError):
        thresholds_valid = False
    if not thresholds_valid:
        raise RuntimeError(
            "ADAPTIVE_WEAK_THRESHOLD and ADAPTIVE_STRONG_THRESHOLD must be numbers from 0 to 10, with weak below strong."
        )
    app.config["ADAPTIVE_STRONG_THRESHOLD"] = float(strong_threshold)
    app.config["ADAPTIVE_WEAK_THRESHOLD"] = float(weak_threshold)
    if app.config.get("LOG_LEVEL", "INFO") not in ("DEBUG", "INFO"):
        raise RuntimeError("LOG_LEVEL must be DEBUG or INFO.")
    if app.config["STORAGE_BACKEND"] == "r2":
        required = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")
        missing = [key for key in required if not app.config.get(key)]
        if missing:
            raise RuntimeError(f"R2 storage selected but configuration is missing: {', '.join(missing)}.")
    if app.config["STORAGE_BACKEND"] == "s3":
        if not app.config.get("S3_BUCKET_NAME"):
            raise RuntimeError("S3_BUCKET_NAME is required when STORAGE_BACKEND=s3.")
        if bool(app.config.get("AWS_ACCESS_KEY_ID")) != bool(app.config.get("AWS_SECRET_ACCESS_KEY")):
            raise RuntimeError("Set both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or leave both empty to use the AWS credential chain.")
        if app.config.get("S3_ADDRESSING_STYLE") not in ("auto", "virtual", "path"):
            raise RuntimeError("S3_ADDRESSING_STYLE must be auto, virtual, or path.")
        endpoint = app.config.get("S3_ENDPOINT_URL")
        if endpoint:
            try:
                parsed_endpoint = make_url(endpoint)
            except Exception as exc:
                raise RuntimeError("S3_ENDPOINT_URL must be a valid HTTP or HTTPS URL.") from exc
            if parsed_endpoint.drivername not in ("http", "https") or not parsed_endpoint.host:
                raise RuntimeError("S3_ENDPOINT_URL must be a valid HTTP or HTTPS URL.")

    if app.config.get("JWT_EXP_HOURS", 0) <= 0:
        raise RuntimeError("JWT_EXP_HOURS must be a positive integer.")
