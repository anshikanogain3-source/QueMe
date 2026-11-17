"""Local interview intelligence powered by Ollama's chat API."""
import json
import fcntl
import logging
import math
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from contextlib import contextmanager
from pathlib import Path

from flask import current_app

logger = logging.getLogger(__name__)
DEFAULT_OLLAMA_MODEL = "qwen3:1.7b"
_MAX_JSON_ATTEMPTS = 2
_INVALID_STRUCTURED_RESPONSE = "Local Ollama returned invalid structured content after permitted attempts."


class InvalidStructuredResponse(ValueError):
    def __init__(self, category, attempts):
        super().__init__(_INVALID_STRUCTURED_RESPONSE)
        self.category = category
        self.attempts = attempts


def _configured():
    # This checks configuration only. Runtime/model availability is checked against /api/tags.
    return bool(current_app.config.get("OLLAMA_BASE_URL"))


def _ollama_base_url():
    return (current_app.config.get("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")


def _ollama_timeout():
    return current_app.config.get("OLLAMA_TIMEOUT", 300)


class OllamaLockTimeout(TimeoutError):
    """Raised when another local Ollama request holds the shared process lock."""


@contextmanager
def _ollama_process_lock(*, operation="generation", correlation_id=None, attempt=1):
    """Serialize this app's Ollama calls across its web and worker processes."""
    lock_dir = Path(current_app.instance_path)
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / "ollama-inference.lock").open("a+") as lock_file:
        waiting = time.monotonic()
        correlation = correlation_id or "-"
        logger.info(
            "Ollama lock wait started operation=%s correlation_id=%s attempt=%d",
            operation, correlation, attempt,
        )
        timeout = current_app.config.get("OLLAMA_LOCK_WAIT_TIMEOUT", 30)
        try:
            while True:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() - waiting >= timeout:
                        raise OllamaLockTimeout("Timed out waiting for the shared Ollama inference lock.")
                    time.sleep(0.05)
        except Exception as exc:
            logger.warning(
                "Ollama lock acquisition failed operation=%s correlation_id=%s attempt=%d "
                "lock_wait_ms=%d error_type=%s",
                operation, correlation, attempt,
                int((time.monotonic() - waiting) * 1000), type(exc).__name__,
            )
            raise
        lock_wait_ms = (time.monotonic() - waiting) * 1000
        logger.info(
            "Ollama lock acquired operation=%s correlation_id=%s attempt=%d lock_wait_ms=%d",
            operation, correlation, attempt, int(lock_wait_ms),
        )
        try:
            yield lock_wait_ms
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_http_error(exc: HTTPError, *, model: str, endpoint: str):
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        detail = payload.get("error") if isinstance(payload, dict) else None
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        detail = None
    if exc.code == 404 and detail and "model" in detail.lower() and "not found" in detail.lower():
        return f"Local Ollama model '{model}' is not installed. Pull it with `ollama pull {model}`."
    if detail:
        return f"Local Ollama {endpoint} request failed (HTTP {exc.code}): {str(detail)[:300]}"
    return f"Local Ollama {endpoint} request failed (HTTP {exc.code})."


def _connection_error(exc, *, base_url: str, timeout: int):
    reason = exc.reason if isinstance(exc, URLError) else exc
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return f"Local Ollama request to {base_url} timed out after {timeout} seconds."
    detail = str(reason).strip() or type(reason).__name__
    return f"Local Ollama connection to {base_url} failed: {detail}"


def _check_model_available():
    """Check the actual configured Ollama server and ensure the exact model is installed."""
    base_url = _ollama_base_url()
    model = current_app.config.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL
    timeout = min(_ollama_timeout(), 10)
    request = Request(f"{base_url}/api/tags", headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(_read_http_error(exc, model=model, endpoint="/api/tags")) from None
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise RuntimeError(_connection_error(exc, base_url=base_url, timeout=timeout)) from None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"Local Ollama /api/tags returned invalid JSON: {exc}") from None

    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise RuntimeError("Local Ollama /api/tags returned an unexpected response; expected a models list.")
    installed = {
        item.get("name")
        for item in models
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if model not in installed:
        raise RuntimeError(f"Local Ollama model '{model}' is not installed. Pull it with `ollama pull {model}`.")


def _generate(prompt: str, *, num_predict=700, operation="generation", correlation_id=None, attempt=1):
    """Call the configured local Ollama server; never fall back to a cloud API."""
    base_url = _ollama_base_url()
    model = current_app.config.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL
    timeout = _ollama_timeout()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "think": False,
        "keep_alive": current_app.config.get("OLLAMA_KEEP_ALIVE", "30m"),
        "options": {
            "temperature": current_app.config.get("OLLAMA_TEMPERATURE", 0.2),
            "num_predict": num_predict,
            "num_ctx": current_app.config.get("OLLAMA_NUM_CTX", 4096),
        },
    }
    request = Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    request_started = None
    correlation = correlation_id or "-"
    try:
        with _ollama_process_lock(
            operation=operation, correlation_id=correlation_id, attempt=attempt
        ) as lock_wait_ms:
            request_started = time.monotonic()
            logger.info(
                "Ollama request started operation=%s correlation_id=%s attempt=%d model=%s timeout_s=%s num_predict=%d",
                operation, correlation, attempt, model, timeout, num_predict,
            )
            with urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        content = result.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned an empty response")
        eval_duration_ns = result.get("eval_duration")
        eval_count = result.get("eval_count")
        tokens_per_second = (
            eval_count / (eval_duration_ns / 1_000_000_000)
            if isinstance(eval_count, (int, float))
            and isinstance(eval_duration_ns, (int, float))
            and eval_duration_ns > 0
            else None
        )
        logger.info(
            "Ollama request completed operation=%s correlation_id=%s attempt=%d model=%s wall_ms=%d request_ms=%d "
            "lock_wait_ms=%d load_ms=%s prompt_eval_ms=%s generation_ms=%s "
            "ollama_total_ms=%s prompt_tokens=%s generated_tokens=%s tokens_per_second=%s num_predict=%d",
            operation,
            correlation,
            attempt,
            model,
            int((time.monotonic() - started) * 1000),
            int((time.monotonic() - request_started) * 1000),
            int(lock_wait_ms),
            _duration_ms(result.get("load_duration")),
            _duration_ms(result.get("prompt_eval_duration")),
            _duration_ms(eval_duration_ns),
            _duration_ms(result.get("total_duration")),
            result.get("prompt_eval_count"),
            eval_count,
            round(tokens_per_second, 2) if tokens_per_second is not None else None,
            num_predict,
        )
        return content
    except HTTPError as exc:
        logger.warning(
            "Ollama request failed operation=%s correlation_id=%s attempt=%d model=%s "
            "request_ms=%s wall_ms=%d http_status=%d",
            operation, correlation, attempt, model,
            int((time.monotonic() - request_started) * 1000) if request_started else None,
            int((time.monotonic() - started) * 1000), exc.code,
        )
        raise RuntimeError(_read_http_error(exc, model=model, endpoint="/api/chat")) from None
    except OllamaLockTimeout as exc:
        logger.warning(
            "Ollama lock wait timed out operation=%s correlation_id=%s attempt=%d model=%s "
            "lock_wait_ms=%d timeout_s=%s",
            operation, correlation, attempt, model,
            int((time.monotonic() - started) * 1000),
            current_app.config.get("OLLAMA_LOCK_WAIT_TIMEOUT", 30),
        )
        raise RuntimeError(
            f"Local Ollama lock wait timed out after {current_app.config.get('OLLAMA_LOCK_WAIT_TIMEOUT', 30)} seconds."
        ) from exc
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        is_timeout = isinstance(reason, (TimeoutError, socket.timeout))
        logger.warning(
            "Ollama request %s operation=%s correlation_id=%s attempt=%d model=%s "
            "request_ms=%s wall_ms=%d error_type=%s",
            "timed out" if is_timeout else "failed",
            operation, correlation, attempt, model,
            int((time.monotonic() - request_started) * 1000) if request_started else None,
            int((time.monotonic() - started) * 1000), type(reason).__name__,
        )
        raise RuntimeError(_connection_error(exc, base_url=base_url, timeout=timeout)) from None
    except (json.JSONDecodeError, AttributeError, ValueError):
        logger.warning(
            "Ollama response invalid operation=%s correlation_id=%s attempt=%d model=%s "
            "request_ms=%s wall_ms=%d",
            operation, correlation, attempt, model,
            int((time.monotonic() - request_started) * 1000) if request_started else None,
            int((time.monotonic() - started) * 1000),
        )
        raise RuntimeError("Local Ollama returned an invalid response.") from None


def _parse_json(text: str):
    if not isinstance(text, str) or not text.strip():
        return None
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
        start, end = text.find("["), text.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _generate_json(
    prompt, *, num_predict=700, validator=None, operation="generation",
    correlation_id=None, soft_budget_seconds=None, return_attempts=False,
):
    """Retry a malformed/invalid structured response once, with a repair instruction."""
    started = time.monotonic()
    last_category = "invalid_json"
    for attempt in range(_MAX_JSON_ATTEMPTS):
        logger.info(
            "Ollama structured response attempt operation=%s correlation_id=%s attempt=%d max_attempts=%d",
            operation, correlation_id or "-", attempt + 1, _MAX_JSON_ATTEMPTS,
        )
        request_prompt = prompt if attempt == 0 else (
            "Your previous response was invalid. Return only valid JSON matching the requested structure.\n" + prompt
        )
        content = _generate(
            request_prompt,
            num_predict=num_predict,
            operation=operation,
            correlation_id=correlation_id,
            attempt=attempt + 1,
        )
        data = _parse_json(content)
        valid = data is not None and (validator is None or validator(data))
        if valid:
            return (data, attempt + 1) if return_attempts else data
        reason = "invalid_json" if data is None else "validation_failed"
        last_category = "invalid_json" if data is None else "schema_validation"
        logger.warning(
            "Ollama structured response rejected operation=%s correlation_id=%s attempt=%d "
            "reason=%s retrying=%s",
            operation, correlation_id or "-", attempt + 1, reason,
            attempt + 1 < _MAX_JSON_ATTEMPTS and (
                soft_budget_seconds is None
                or time.monotonic() - started < soft_budget_seconds
            ),
        )
        if attempt + 1 < _MAX_JSON_ATTEMPTS:
            if soft_budget_seconds is not None and time.monotonic() - started >= soft_budget_seconds:
                logger.warning(
                    "Ollama structured repair skipped operation=%s correlation_id=%s reason=soft_budget_exceeded",
                    operation, correlation_id or "-",
                )
                break
    raise InvalidStructuredResponse(last_category, attempt + 1)


def _evaluation_token_budget(criterion_count):
    """Bound output allowance while reserving room for every rubric criterion."""
    minimum = int(current_app.config.get("OLLAMA_EVALUATION_MIN_TOKENS", 700))
    maximum = int(current_app.config.get("OLLAMA_EVALUATION_MAX_TOKENS", 1800))
    return min(maximum, minimum + max(0, criterion_count) * 55)


def _valid_evaluation_response(value, criterion_names):
    if not isinstance(value, dict):
        return False
    scores = value.get("criteria_scores", value.get("criterion_scores"))
    details = value.get("criterion_details")
    if not isinstance(scores, dict) or not isinstance(details, dict):
        return False
    if set(scores) != set(criterion_names) or set(details) != set(criterion_names):
        return False
    for name in criterion_names:
        score = scores.get(name)
        detail = details.get(name)
        if (
            isinstance(score, bool) or not isinstance(score, (int, float))
            or not math.isfinite(score) or not 0 <= score <= 10
            or not isinstance(detail, dict)
            or not isinstance(detail.get("applicable"), bool)
            or not isinstance(detail.get("explanation"), str)
            or not detail["explanation"].strip()
            or len(detail["explanation"]) > 500
            or not isinstance(detail.get("evidence_supports_claim"), bool)
            or not isinstance(detail.get("evidence_explanation"), str)
            or len(detail["evidence_explanation"]) > 500
            or "evidence" not in detail
        ):
            return False
        evidence = detail.get("evidence")
        if evidence is not None and not isinstance(evidence, str):
            return False
    return (
        isinstance(value.get("question_relevant"), bool)
        and isinstance(value.get("relevance_explanation"), str)
        and bool(value["relevance_explanation"].strip())
        and value.get("accuracy_category") in {
            "CORRECT_COMPLETE", "MOSTLY_CORRECT_INCOMPLETE", "PARTIALLY_CORRECT",
            "INCORRECT_OR_IRRELEVANT", "INSUFFICIENT_EVIDENCE",
        }
        and isinstance(value.get("technical_accuracy"), str) and bool(value["technical_accuracy"].strip())
        and isinstance(value.get("missing_concepts"), list)
        and all(isinstance(item, str) for item in value["missing_concepts"])
        and isinstance(value.get("correct_explanation"), str) and bool(value["correct_explanation"].strip())
        and isinstance(value.get("strengths"), list)
        and len(value["strengths"]) <= 2
        and all(isinstance(item, str) for item in value["strengths"])
        and isinstance(value.get("weaknesses"), list)
        and len(value["weaknesses"]) <= 2
        and all(isinstance(item, str) for item in value["weaknesses"])
        and isinstance(value.get("feedback"), str) and bool(value["feedback"].strip())
        and isinstance(value.get("needs_teacher_review"), bool)
        and isinstance(value.get("incorrect_claims"), list)
        and all(isinstance(item, str) for item in value["incorrect_claims"])
        and isinstance(value.get("correct_concepts"), list)
        and all(isinstance(item, str) for item in value["correct_concepts"])
        and isinstance(value.get("suggested_improvements"), list)
        and all(isinstance(item, str) for item in value["suggested_improvements"])
        and value.get("completeness") in {"COMPLETE", "INCOMPLETE", "SUBSTANTIALLY_INCORRECT"}
    )


def _contains_google_error_detail(details, type_name):
    if isinstance(details, dict):
        detail_type = details.get("@type")
        if isinstance(detail_type, str) and detail_type.rsplit(".", 1)[-1] == type_name:
            return True
        return any(_contains_google_error_detail(value, type_name) for value in details.values())
    if isinstance(details, (list, tuple)):
        return any(_contains_google_error_detail(value, type_name) for value in details)
    return False


def _contains_google_error_reason(details, reasons):
    if isinstance(details, dict):
        reason = details.get("reason")
        if isinstance(reason, str) and reason.casefold().replace("-", "_") in reasons:
            return True
        return any(_contains_google_error_reason(value, reasons) for value in details.values())
    if isinstance(details, (list, tuple)):
        return any(_contains_google_error_reason(value, reasons) for value in details)
    return False


def _provider_error_category(exc):
    """Classify provider failures without retaining exception text or secrets."""
    name = type(exc).__name__.casefold()
    message = str(getattr(exc, "message", None) or str(exc)).casefold()
    code = getattr(exc, "code", None)
    if isinstance(exc, InvalidStructuredResponse):
        return exc.category
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return "configuration"
    status_match = re.search(r"http\s+(\d{3})", message)
    status_code = int(status_match.group(1)) if status_match else None
    if isinstance(exc, (TimeoutError, socket.timeout)) or "timeout" in name or "timed out" in message:
        return "timeout"
    if code in (401, 403) or status_code in (401, 403) or any(term in message for term in ("unauthorized", "permission_denied", "api key", "authentication")):
        return "authentication"

    details = getattr(exc, "details", None)
    if (
        _contains_google_error_detail(details, "QuotaFailure")
        or _contains_google_error_reason(details, {"quota_exceeded", "daily_quota_exceeded", "project_quota_exceeded"})
    ):
        return "quota_exhausted"
    is_rate_limit = (
        any(term in message for term in (
            "rate limit", "rate_limit", "too many requests", "per minute", "per-minute",
            "per second", "per-second", "retry after", "retry in", "retrydelay",
        ))
        or _contains_google_error_detail(details, "RetryInfo")
        or _contains_google_error_reason(details, {"rate_limit", "rate_limit_exceeded"})
    )
    if is_rate_limit:
        return "rate_limit"

    quota_exhaustion = any(term in message for term in (
        "quota exceeded", "quota_exceeded", "quota exhausted", "quota_exhausted",
        "daily quota", "daily limit", "per day", "per-day", "project quota",
    )) or ("quota" in message and any(term in message for term in ("exceed", "exhaust", "billing")))
    if quota_exhaustion:
        return "quota_exhausted"

    if code == 429 or status_code == 429:
        return "unknown_rate_limit"
    if status_code is not None and status_code >= 500:
        return "network"
    if isinstance(exc, (URLError, ConnectionError, OSError)) or any(term in name for term in ("connection", "network")) or any(term in message for term in ("connection", "network")):
        return "network"
    if isinstance(exc, ValueError):
        if "invalid json" in message:
            return "invalid_json"
        if "invalid structured evaluation" in message:
            return "schema_validation"
        return "provider_error"
    return "provider_error"


def _failure_is_retryable(category):
    return category in {"timeout", "rate_limit", "network"}


def _generate_gemini_json(prompt, criterion_names):
    """Generate one structured evaluation. Worker retries are bounded by MAX_ATTEMPTS."""
    api_key = current_app.config.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Gemini evaluation is not configured.")
    from google import genai
    from google.genai import types

    criterion_names = criterion_names or ["Overall"]
    criterion_properties = {
        name: {"type": "OBJECT", "properties": {
            "applicable": {"type": "BOOLEAN"},
            "explanation": {"type": "STRING"},
            "evidence": {"type": ["STRING", "NULL"]},
            "evidence_supports_claim": {"type": "BOOLEAN"},
            "evidence_explanation": {"type": "STRING"},
        }, "required": ["applicable", "explanation", "evidence", "evidence_supports_claim", "evidence_explanation"]}
        for name in criterion_names
    }
    schema = {
        "type": "OBJECT",
        "properties": {
            "criteria_scores": {"type": "OBJECT", "properties": {name: {"type": "NUMBER"} for name in criterion_names}},
            "criterion_details": {"type": "OBJECT", "properties": criterion_properties},
            "question_relevant": {"type": "BOOLEAN"},
            "relevance_explanation": {"type": "STRING"},
            "accuracy_category": {"type": "STRING", "enum": ["CORRECT_COMPLETE", "MOSTLY_CORRECT_INCOMPLETE", "PARTIALLY_CORRECT", "INCORRECT_OR_IRRELEVANT", "INSUFFICIENT_EVIDENCE"]},
            "technical_accuracy": {"type": "STRING"}, "missing_concepts": {"type": "ARRAY", "items": {"type": "STRING"}},
            "correct_explanation": {"type": "STRING"}, "strengths": {"type": "ARRAY", "items": {"type": "STRING"}},
            "weaknesses": {"type": "ARRAY", "items": {"type": "STRING"}}, "feedback": {"type": "STRING"},
            "needs_teacher_review": {"type": "BOOLEAN"},
            "incorrect_claims": {"type": "ARRAY", "items": {"type": "STRING"}},
            "correct_concepts": {"type": "ARRAY", "items": {"type": "STRING"}},
            "suggested_improvements": {"type": "ARRAY", "items": {"type": "STRING"}},
            "completeness": {"type": "STRING", "enum": ["COMPLETE", "INCOMPLETE", "SUBSTANTIALLY_INCORRECT"]},
        },
        "required": ["criteria_scores", "criterion_details", "question_relevant", "relevance_explanation", "accuracy_category", "technical_accuracy", "missing_concepts", "correct_explanation", "strengths", "weaknesses", "feedback", "needs_teacher_review", "incorrect_claims", "correct_concepts", "suggested_improvements", "completeness"],
    }
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=int(current_app.config.get("GEMINI_EVALUATION_TIMEOUT", 30)) * 1000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=current_app.config.get("GEMINI_EVALUATION_MODEL") or "gemini-3.5-flash-lite",
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=0.1),
                )
                data = _parse_json(response.text)
                if data is None:
                    raise ValueError("Gemini returned invalid JSON.")
                return data, attempt + 1
            except Exception as exc:
                category = _provider_error_category(exc)
                retryable = _failure_is_retryable(category)
                logger.warning(
                    "Evaluation provider request failed provider=gemini model=%s attempt=%d "
                    "error_category=%s retryable=%s",
                    current_app.config.get("GEMINI_EVALUATION_MODEL") or "gemini-3.5-flash-lite",
                    attempt + 1, category, retryable,
                )
                if attempt == 1 or not retryable:
                    raise
                time.sleep(1)
    finally:
        client.close()


def _duration_ms(value):
    if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
        return round(value / 1_000_000, 2)
    return None


def _error_message(exc):
    message = str(exc)
    return message if message.startswith("Local Ollama") else "Local Ollama could not complete this request. Try again or ask a teacher to review it."


def generate_questions(topic: str, question_type: str, difficulty: str, count: int = 10):
    if not _configured():
        return {"available": False, "questions": [], "error": "Local interview generation is not configured."}
    started = time.monotonic()
    logger.info(
        "AI question generation started model=%s type=%s difficulty=%s count=%d",
        current_app.config.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL,
        question_type,
        difficulty,
        count,
    )
    prompt = (
        f"Generate {count} campus placement interview questions. Questions should be clear and suitable for the requested level.\n"
        f"Topic or technical domain: {topic}\nInterview type: {question_type}\nDifficulty: {difficulty}\n"
        "Return a JSON object containing a questions array. Each item must contain question_text, question_type, difficulty, expected_key_points."
    )
    try:
        _check_model_available()

        def valid_questions(value):
            rows = value if isinstance(value, list) else value.get("questions") if isinstance(value, dict) and isinstance(value.get("questions"), list) else [value]
            return bool(rows) and all(
                isinstance(item, dict) and isinstance(item.get("question_text"), str) and item["question_text"].strip()
                for item in rows
            )

        data = _generate_json(prompt, num_predict=1400, validator=valid_questions)
        questions = data if isinstance(data, list) else data.get("questions") if isinstance(data, dict) and isinstance(data.get("questions"), list) else [data]
        questions = questions[:max(1, min(int(count), 10))]
        if questions:
            logger.info("AI question generation completed count=%d duration_ms=%d", len(questions), int((time.monotonic() - started) * 1000))
            return {"available": True, "questions": questions}
        logger.warning("AI question generation returned no questions duration_ms=%d", int((time.monotonic() - started) * 1000))
        return {"available": False, "questions": [], "error": "Local Ollama did not generate any questions. Try again."}
    except Exception as exc:
        logger.warning("AI question generation failed error_type=%s duration_ms=%d", type(exc).__name__, int((time.monotonic() - started) * 1000))
        return {"available": False, "questions": [], "error": _error_message(exc)}


def _evaluate_answer_single(payload: dict, *, correlation_id=None, provider_override=None):
    provider_attempts = 0
    fallback = {
        "criteria_scores": {}, "strengths": [],
        "weaknesses": ["Automatic evaluation is unavailable."],
        "feedback": "Teacher review is recommended because automatic evaluation is unavailable.",
        "needs_teacher_review": True, "content_score": None,
        "evaluation_status": "UNAVAILABLE", "accuracy_category": "INSUFFICIENT_EVIDENCE",
        "question_relevant": False, "relevance_explanation": "Relevance could not be assessed.",
    }
    provider = provider_override or current_app.config.get("EVALUATION_PROVIDER", "ollama")
    model = (
        current_app.config.get("GEMINI_EVALUATION_MODEL") or "gemini-3.5-flash-lite"
        if provider == "gemini" else current_app.config.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL
    )
    if provider == "ollama" and not _configured():
        logger.warning("Answer evaluation unavailable provider=ollama model=%s error_category=configuration", current_app.config.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL)
        fallback["error"] = "Local Ollama is not configured."
        fallback["error_category"] = "configuration"
        return fallback
    if provider == "gemini" and not current_app.config.get("GEMINI_API_KEY"):
        logger.warning("Answer evaluation unavailable provider=gemini model=%s error_category=configuration", current_app.config.get("GEMINI_EVALUATION_MODEL") or "gemini-3.5-flash-lite")
        fallback["error"] = "Gemini evaluation is not configured."
        fallback["error_category"] = "configuration"
        return fallback
    rubric = payload.get("rubric") or {}
    criteria = rubric.get("criteria", []) if isinstance(rubric, dict) else []
    criteria = [item for item in criteria if isinstance(item, (str, dict))]
    criterion_names = [item if isinstance(item, str) else item.get("name") for item in criteria]
    criterion_names = [name for name in criterion_names if isinstance(name, str) and name.strip()]
    validation_names = criterion_names or ["Overall"]
    criterion_weights = {}
    for item in criteria:
        if isinstance(item, dict):
            name, weight = item.get("name"), item.get("weight")
            if isinstance(name, str) and isinstance(weight, (int, float)) and not isinstance(weight, bool) and math.isfinite(weight) and weight >= 0:
                criterion_weights[name] = float(weight)
    if len(criterion_weights) != len(criterion_names):
        criterion_weights = {name: 1.0 for name in criterion_names}
    weight_total = sum(criterion_weights.values())
    if weight_total:
        criterion_weights = {name: weight * 100 / weight_total for name, weight in criterion_weights.items()}

    transcript = str(payload.get("transcript") or "").strip()
    if not transcript:
        fallback["error"] = "No usable transcript was available for evaluation."
        fallback["error_category"] = "invalid_input"
        return fallback
    no_answer = transcript.casefold().strip(" .,!\t\n") in {"i don't know", "i do not know", "don't know", "do not know", "no idea"}
    if no_answer and provider_override is None:
        names = criterion_names or ["Answer" ]
        return {
            "criteria_scores": {name: 0.0 for name in names},
            "criterion_details": {name: {"applicable": True, "explanation": "No answer provided.", "evidence": None, "evidence_explanation": ""} for name in names},
            "criteria_weights": criterion_weights or {name: 100.0 / len(names) for name in names},
            "content_score": 0.0, "strengths": [], "weaknesses": ["No answer was provided."],
            "missing_concepts": [], "correct_explanation": "Review the question's expected answer and try again.",
            "technical_accuracy": "Not answered", "feedback": "No answer was provided. Review the question and try again.", "needs_teacher_review": False,
            "question_relevant": False, "relevance_explanation": "No substantive answer was provided.",
            "accuracy_category": "INCORRECT_OR_IRRELEVANT",
            "_provider_attempt_count": 0,
        }

    # Rubric is supplied once. Delivery metrics remain in persisted analytics and
    # score calculations; they are not repeated in the content-evaluation prompt.
    evaluation_input = {
        key: value for key, value in payload.items()
        if key not in ("rubric", "audio_metrics")
    }
    prompt = (
        "Evaluate the candidate answer against the question, reference answer and every rubric criterion. "
        "When no rubric criteria are supplied, score one criterion named Overall. First identify the question's central intent and answer it directly; "
        "topic similarity alone is not relevance. Identify incorrect claims, contradictions, correct concepts, and important omissions. "
        "For each criterion, provide an exact transcript excerpt, "
        "evidence_supports_claim (boolean), and evidence_explanation stating why that excerpt supports the criterion score. "
        "Set evidence_supports_claim false if the excerpt is missing, unrelated, or merely shares a keyword. "
        "A transcript substring match proves only that the words were spoken, not that the claim is true or relevant. "
        "First decide question_relevant based on meaning, not keyword overlap, and provide relevance_explanation. If false, all content scores must be zero, "
        "accuracy_category must be INCORRECT_OR_IRRELEVANT, strengths must be empty, and feedback must not praise accuracy. "
        "Set accuracy_category to CORRECT_COMPLETE, MOSTLY_CORRECT_INCOMPLETE, PARTIALLY_CORRECT, "
        "INCORRECT_OR_IRRELEVANT, or INSUFFICIENT_EVIDENCE. Every positive claim needs exact transcript evidence that "
        "supports that claim; evidence that is merely present but unrelated does not support it. "
        "Score only demonstrated correctness, from 0 to 10. Return complete JSON with criteria_scores containing "
        "a score for every criterion and criterion_details containing every criterion with applicable (boolean), "
        "a concise non-empty explanation (at most 2 sentences), and evidence (an exact transcript excerpt or null). "
        "Also return technical_accuracy (brief string), missing_concepts (string array), correct_explanation (brief string), "
        "strengths and weaknesses (arrays of at most 2 concise strings each), feedback (brief string), and "
        "incorrect_claims, correct_concepts, and suggested_improvements (string arrays), completeness "
        "(COMPLETE, INCOMPLETE, or SUBSTANTIALLY_INCORRECT), "
        "needs_teacher_review (boolean). Never invent or rewrite evidence. Keep JSON complete; do not omit criteria or fields.\n"
        f"Rubric: {json.dumps(criteria or [{'name': 'Overall', 'weight': 100}], ensure_ascii=False, separators=(',', ':'))}\n"
        f"Evaluation input: {json.dumps(evaluation_input, ensure_ascii=False, separators=(',', ':'))}"
    )
    evaluation_started = time.monotonic()
    token_budget = _evaluation_token_budget(len(criterion_names))
    soft_budget = int(current_app.config.get("OLLAMA_EVALUATION_BUDGET_SECONDS", 600))
    logger.info(
        "Answer evaluation started correlation_id=%s provider=%s model=%s criteria=%d output_token_budget=%d soft_budget_s=%d",
        correlation_id or "-",
        provider, model,
        len(criterion_names),
        token_budget,
        soft_budget,
    )
    try:
        if provider == "gemini":
            generated = _generate_gemini_json(prompt, validation_names)
            data, provider_attempts = generated if isinstance(generated, tuple) else (generated, 1)
            if not _valid_evaluation_response(data, validation_names):
                raise ValueError("Gemini returned invalid structured evaluation.")
        else:
            data, provider_attempts = _generate_json(
                prompt, num_predict=token_budget,
                validator=lambda value: _valid_evaluation_response(value, validation_names),
                operation="answer_evaluation", correlation_id=correlation_id,
                soft_budget_seconds=soft_budget,
                return_attempts=True,
            )
        scores = data.get("criteria_scores", data.get("criterion_scores", {}))
        details = data.get("criterion_details", {})
        clean_scores, clean_details = {}, {}
        evidence_unavailable = False
        for name in validation_names:
            detail = details.get(name, {})
            applicable = detail.get("applicable", True) is not False
            explanation = detail.get("explanation", "")
            evidence = detail.get("evidence")
            evidence_explanation = detail.get("evidence_explanation", "")
            validated_evidence = None
            if isinstance(evidence, str) and evidence.strip() and len(evidence.strip()) <= 240:
                index = transcript.casefold().find(evidence.strip().casefold())
                if index >= 0:
                    validated_evidence = transcript[index:index + len(evidence.strip())]
            score_value = scores.get(name)
            positive_score = isinstance(score_value, (int, float)) and not isinstance(score_value, bool) and score_value > 0
            evidence_supports_claim = detail.get("evidence_supports_claim") is True
            if applicable and positive_score and (
                validated_evidence is None or not evidence_explanation.strip() or not evidence_supports_claim
            ):
                evidence_unavailable = True
            clean_details[name] = {
                "applicable": applicable,
                "explanation": explanation.strip(),
                "evidence": validated_evidence,
                "evidence_supports_claim": evidence_supports_claim,
                "evidence_explanation": evidence_explanation.strip() if validated_evidence else "",
            }
            if applicable:
                try:
                    value = float(scores[name])
                except (KeyError, TypeError, ValueError):
                    continue
                if math.isfinite(value) and 0 <= value <= 10:
                    clean_scores[name] = round(value, 2)
        applicable_count = sum(item["applicable"] for item in clean_details.values())
        semantic_review_required = any(score > 0 for score in clean_scores.values())
        if not criterion_names and "Overall" in clean_scores:
            criterion_weights = {"Overall": 100.0}
        applicable_weight = sum(criterion_weights.get(name, 0) for name in clean_scores)
        content_score = round(sum(score * criterion_weights.get(name, 0) for name, score in clean_scores.items()) / applicable_weight, 2) if applicable_weight else None
        category = data["accuracy_category"]
        question_relevant = data["question_relevant"]
        category_conflict = bool(
            content_score is not None and content_score > 0
            and category == "INCORRECT_OR_IRRELEVANT"
        )
        if data.get("completeness") == "SUBSTANTIALLY_INCORRECT" and content_score is not None and content_score > 0:
            clean_scores = {name: 0.0 for name in clean_scores}
            content_score = 0.0 if clean_scores else None
            category = "INCORRECT_OR_IRRELEVANT"
            category_conflict = True
        if not question_relevant or category == "INCORRECT_OR_IRRELEVANT":
            clean_scores = {name: 0.0 for name in clean_scores}
            content_score = 0.0 if clean_scores else None
            category = "INCORRECT_OR_IRRELEVANT"
        elif category == "INSUFFICIENT_EVIDENCE" or evidence_unavailable or content_score is None:
            content_score = None
            category = "INSUFFICIENT_EVIDENCE"
        if content_score is not None:
            score_category = (
                "CORRECT_COMPLETE" if content_score >= 9 else
                "MOSTLY_CORRECT_INCOMPLETE" if content_score >= 7 else
                "PARTIALLY_CORRECT" if content_score >= 3 else
                "INCORRECT_OR_IRRELEVANT"
            )
            category_conflict = category_conflict or category != score_category
            category = score_category
        strengths, weaknesses = data.get("strengths", []), data.get("weaknesses", [])
        clean_strings = lambda values: [item.strip()[:300] for item in values if isinstance(item, str) and item.strip()] if isinstance(values, list) else []
        if not question_relevant or category in ("INCORRECT_OR_IRRELEVANT", "INSUFFICIENT_EVIDENCE"):
            strengths = []
        feedback = data.get("feedback")
        correct_explanation = data.get("correct_explanation")
        technical_accuracy = data.get("technical_accuracy")
        if not question_relevant:
            clean_details = {
                name: {
                    "applicable": detail["applicable"],
                    "explanation": "No relevant technical claim was demonstrated for this question.",
                    "evidence": None,
                    "evidence_supports_claim": False,
                    "evidence_explanation": "",
                }
                for name, detail in clean_details.items()
            }
            weaknesses = ["The answer does not address the question."]
            feedback = "The response does not address the question. Teacher review is recommended."
            correct_explanation = "The response did not demonstrate the requested concept."
            technical_accuracy = "Incorrect or irrelevant to the question."
        elif category == "INCORRECT_OR_IRRELEVANT":
            clean_details = {
                name: {
                    "applicable": detail["applicable"],
                    "explanation": "The response did not demonstrate correct technical content.",
                    "evidence": None,
                    "evidence_supports_claim": False,
                    "evidence_explanation": "",
                }
                for name, detail in clean_details.items()
            }
            weaknesses = ["The answer does not demonstrate correct technical content."]
            feedback = "The answer does not demonstrate correct technical content. Teacher review is recommended."
            correct_explanation = "The response did not demonstrate the requested concept."
            technical_accuracy = "Incorrect."
        elif category == "INSUFFICIENT_EVIDENCE":
            clean_scores = {}
            clean_details = {
                name: {
                    "applicable": True,
                    "explanation": "Insufficient transcript evidence to evaluate this claim.",
                    "evidence": None,
                    "evidence_supports_claim": False,
                    "evidence_explanation": "",
                }
                for name in validation_names
            }
            strengths = []
            weaknesses = ["The transcript does not contain verifiable supporting evidence."]
            correct_explanation = "No answer explanation is shown because supporting evidence could not be verified."
            technical_accuracy = "Insufficient evidence to assess technical accuracy."
            missing_concepts = []
            feedback = "The transcript does not provide enough relevant evidence to score this answer. Teacher review is recommended."
        result = {
            **data, "criteria_scores": clean_scores, "criteria_weights": criterion_weights,
            "criterion_details": clean_details, "content_score": content_score,
            "evaluation_status": "COMPLETED" if content_score is not None else "UNAVAILABLE",
            "accuracy_category": category, "question_relevant": question_relevant,
            "strengths": clean_strings(strengths), "weaknesses": clean_strings(weaknesses),
            "missing_concepts": clean_strings(missing_concepts if category == "INSUFFICIENT_EVIDENCE" else data.get("missing_concepts", [])),
            "correct_explanation": correct_explanation.strip()[:1200] if isinstance(correct_explanation, str) else "",
            "technical_accuracy": technical_accuracy.strip()[:300] if isinstance(technical_accuracy, str) else "",
            "feedback": feedback.strip()[:1000] if isinstance(feedback, str) else "",
            "needs_teacher_review": bool(data.get("needs_teacher_review", False)) or semantic_review_required or category_conflict or not question_relevant or category == "INSUFFICIENT_EVIDENCE" or evidence_unavailable or not applicable_count and bool(criterion_names) or bool(applicable_count and len(clean_scores) != applicable_count) or content_score is None,
        }
        if no_answer:
            result.update({
                "criteria_scores": {name: 0.0 for name in validation_names},
                "criterion_details": {name: {
                    "applicable": True, "explanation": "No answer provided.", "evidence": None,
                    "evidence_supports_claim": False, "evidence_explanation": "",
                } for name in validation_names},
                "content_score": 0.0,
                "evaluation_status": "COMPLETED",
                "accuracy_category": "INCORRECT_OR_IRRELEVANT",
                "question_relevant": False,
                "relevance_explanation": "No substantive answer was provided.",
                "feedback": "No answer was provided. Review the question and try again.",
                "needs_teacher_review": False,
            })
        if evidence_unavailable:
            result["review_reason"] = "evidence_unavailable"
        elif semantic_review_required:
            result["review_reason"] = "semantic_support_requires_teacher_review"
        logger.info(
            "Answer evaluation completed correlation_id=%s duration_ms=%d outcome=%s",
            correlation_id or "-",
            int((time.monotonic() - evaluation_started) * 1000),
            "scored" if content_score is not None else "unavailable",
        )
        result["_provider_attempt_count"] = provider_attempts
        return result
    except Exception as exc:
        logger.warning(
            "AI answer evaluation failed correlation_id=%s provider=%s model=%s duration_ms=%d error_category=%s",
            correlation_id or "-",
            provider, model,
            int((time.monotonic() - evaluation_started) * 1000),
            _provider_error_category(exc),
        )
        category = _provider_error_category(exc)
        fallback["error"] = (
            "Evaluation provider request timed out; teacher review is required."
            if category == "timeout" else
            "Evaluation provider returned invalid structured content after permitted attempts."
            if category in {"invalid_json", "schema_validation", "invalid_response"} else
            "Evaluation provider failed; teacher review is required."
        )
        fallback["error_category"] = category
        fallback["retryable"] = _failure_is_retryable(category)
        fallback["_provider_attempt_count"] = int(getattr(exc, "attempts", provider_attempts))
        return fallback


def evaluate_answer(payload: dict, *, correlation_id=None, provider_override=None):
    """Evaluate with one explicitly selected provider; dual orchestration lives above this adapter."""
    provider = provider_override or current_app.config.get("EVALUATION_PROVIDER", "ollama")
    model = (
        current_app.config.get("GEMINI_EVALUATION_MODEL") or "gemini-3.5-flash-lite"
        if provider == "gemini" else current_app.config.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL
    )
    started = time.monotonic()
    result = _evaluate_answer_single(payload, correlation_id=correlation_id, provider_override=provider_override)
    actual_attempt_count = result.get("_provider_attempt_count")
    result["provider_attempt"] = {
        "provider": provider,
        "model": model,
        "status": "FAILED" if result.get("error") else "SKIPPED" if actual_attempt_count == 0 else "SUCCESS",
        "duration_ms": int((time.monotonic() - started) * 1000),
        "attempt_count": result.pop("_provider_attempt_count", 0 if actual_attempt_count == 0 or not payload.get("transcript") else (2 if result.get("retryable") else 1)),
        "error_category": result.get("error_category"),
        "retryable": bool(result.get("retryable", False)),
    }
    return result


def generate_followup(question_text: str, transcript: str, topic_hint: str = ""):
    if not _configured() or not transcript.strip():
        return None
    prompt = (
        "Return JSON only: {\"followup\": string|null}. Generate exactly one short, relevant follow-up question based on the "
        "candidate's answer and original question. Do not repeat the original question or explain your choice. If the answer is complete, "
        "return null.\n"
        f"Original question: {question_text[:1500]}\nType/topic: {topic_hint[:200]}\nCandidate answer: {transcript[:3000]}"
    )
    try:
        data = _generate_json(prompt, num_predict=120, validator=lambda value: isinstance(value, dict) and
            (value.get("followup") is None or isinstance(value.get("followup"), str)))
        followup = data.get("followup")
        return followup.strip()[:500] if isinstance(followup, str) and followup.strip() else None
    except Exception as exc:
        logger.warning("AI follow-up generation failed error_type=%s", type(exc).__name__)
        return None
