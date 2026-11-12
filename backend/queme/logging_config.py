"""Central logging setup for the QueMe Flask application."""
import logging
import re
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import g, has_request_context, request

_LOCK = threading.RLock()
_HANDLER_MARKER = "_queme_logging_handler"
_FILTER_MARKER = "_queme_logging_filter"

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)([\"']?(?:[\w.-]*(?:password|passwd|secret|api[_-]?key|access[_-]?key|authorization|jwt)"
    r"[\w.-]*|(?:access|refresh|id|reset|session|auth)[_-]?token|token)[\"']?)"
    r"(\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_URL_CREDENTIALS = re.compile(r"(?i)(https?://)[^\s/@:]+(?::[^@\s/]+)?@")
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_EMAIL = re.compile(r"\b[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_SQL_PARAMETERS = re.compile(
    r"(?i)(parameters?\s*[:=]\s*)(?:\([^\r\n]*\)|\[[^\r\n]*\]|\{[^\r\n]*\})"
)
_WERKZEUG_ACCESS = re.compile(r'\s-\s-\s\[[^\]]+\]\s".*"\s\d{3}(?:\s|$)')


def _redact(value):
    value = _SECRET_ASSIGNMENT.sub(r"\1\2[REDACTED]", value)
    value = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", value)
    value = _BEARER_TOKEN.sub("Bearer [REDACTED]", value)
    value = _JWT.sub("[REDACTED_JWT]", value)
    value = _EMAIL.sub("[REDACTED_EMAIL]", value)
    return _SQL_PARAMETERS.sub(r"\1[REDACTED]", value)


class RequestContextFilter(logging.Filter):
    """Add safe request context to records without logging user supplied data."""

    _queme_logging_filter = True

    def filter(self, record):
        if has_request_context():
            record.request_id = getattr(g, "request_id", "-")
        else:
            record.request_id = "-"
        return True


class WerkzeugAccessFilter(logging.Filter):
    """Let QueMe's request logger replace Werkzeug's duplicate access lines."""

    _queme_logging_filter = True

    def filter(self, record):
        if record.name.startswith("werkzeug") and record.levelno <= logging.INFO:
            try:
                if _WERKZEUG_ACCESS.search(record.getMessage()):
                    return False
            except Exception:
                return True
        return True


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        record.msg = _redact(message)
        record.args = ()
        if record.exc_info:
            record.exc_text = self.formatException(record.exc_info)
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = _redact(record.exc_text)
        if record.stack_info:
            record.stack_info = _redact(record.stack_info)
        return super().format(record)

    def formatException(self, exc_info):
        return _redact(super().formatException(exc_info))


def _remove_managed_handlers(logger):
    for handler in tuple(logger.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()


def _make_handler(handler, level, formatter):
    handler.setLevel(level)
    handler.setFormatter(formatter)
    handler.addFilter(RequestContextFilter())
    setattr(handler, _HANDLER_MARKER, True)
    return handler


def configure_logging(app):
    """Install console and rotating file handlers once for the current app config."""
    with _LOCK:
        level_name = str(app.config.get("LOG_LEVEL", "INFO")).upper()
        if level_name not in {"DEBUG", "INFO"}:
            raise RuntimeError("LOG_LEVEL must be DEBUG or INFO.")
        level = getattr(logging, level_name)

        log_dir = Path(app.config.get("LOG_DIR", Path(app.root_path).parent / "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        max_bytes = int(app.config.get("LOG_MAX_BYTES", 10 * 1024 * 1024))
        backup_count = int(app.config.get("LOG_BACKUP_COUNT", 5))
        if max_bytes <= 0 or backup_count <= 0:
            raise RuntimeError("LOG_MAX_BYTES and LOG_BACKUP_COUNT must be positive integers.")

        general_formatter = RedactingFormatter(
            "%(asctime)s.%(msecs)03d %(levelname)s [%(name)s] "
            "[request_id=%(request_id)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
        access_formatter = RedactingFormatter(
            "%(asctime)s.%(msecs)03d INFO [access] "
            "[request_id=%(request_id)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )

        root = logging.getLogger()
        _remove_managed_handlers(root)
        root.setLevel(level)
        root.addHandler(_make_handler(logging.StreamHandler(sys.stderr), level, general_formatter))
        root.addHandler(_make_handler(
            RotatingFileHandler(log_dir / "queme.log", maxBytes=max_bytes,
                                backupCount=backup_count, encoding="utf-8"),
            level,
            general_formatter,
        ))
        root.addHandler(_make_handler(
            RotatingFileHandler(log_dir / "errors.log", maxBytes=max_bytes,
                                backupCount=backup_count, encoding="utf-8"),
            logging.WARNING,
            general_formatter,
        ))

        access_logger = logging.getLogger("queme.access")
        _remove_managed_handlers(access_logger)
        access_logger.setLevel(logging.INFO)
        access_logger.propagate = False
        access_logger.addHandler(_make_handler(logging.StreamHandler(sys.stderr), logging.INFO, access_formatter))
        access_logger.addHandler(_make_handler(
            RotatingFileHandler(log_dir / "access.log", maxBytes=max_bytes,
                                backupCount=backup_count, encoding="utf-8"),
            logging.INFO,
            access_formatter,
        ))

        werkzeug_logger = logging.getLogger("werkzeug")
        for filter_ in tuple(werkzeug_logger.filters):
            if getattr(filter_, _FILTER_MARKER, False):
                werkzeug_logger.removeFilter(filter_)
        werkzeug_logger.addFilter(WerkzeugAccessFilter())


def log_api_request(access_logger, started_at, request_id, response):
    """Write one safe access record for an API request."""
    duration_ms = max(0.0, (time.perf_counter() - started_at) * 1000)
    user = getattr(g, "user", None)
    role = getattr(user, "role", "-") or "-"
    access_logger.info(
        "method=%s endpoint=%s status=%d duration_ms=%.2f role=%s",
        request.method,
        request.endpoint or "unmatched",
        response.status_code,
        duration_ms,
        role,
        extra={"request_id": request_id},
    )
