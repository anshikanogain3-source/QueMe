"""Local interview intelligence powered by Ollama's chat API."""
import json
import logging
import math
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app

logger = logging.getLogger(__name__)
DEFAULT_OLLAMA_MODEL = "qwen3.5:4b"
_MAX_JSON_ATTEMPTS = 2


def _configured():
    # This checks configuration only. Runtime/model availability is checked against /api/tags.
    return bool(current_app.config.get("OLLAMA_BASE_URL"))


def _ollama_base_url():
    return (current_app.config.get("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")


def _ollama_timeout():
    return current_app.config.get("OLLAMA_TIMEOUT", 300)


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


def _generate(prompt: str, *, num_predict=700):
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
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned an empty response")
        logger.info(
            "Ollama request model=%s duration_ms=%d prompt_tokens=%s generated_tokens=%s",
            model, int((time.monotonic() - started) * 1000), result.get("prompt_eval_count"), result.get("eval_count"),
        )
        return content
    except HTTPError as exc:
        raise RuntimeError(_read_http_error(exc, model=model, endpoint="/api/chat")) from None
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise RuntimeError(_connection_error(exc, base_url=base_url, timeout=timeout)) from None
    except (json.JSONDecodeError, AttributeError, ValueError):
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


def _generate_json(prompt, *, num_predict=700, validator=None):
    """Retry a malformed/invalid structured response once, with a repair instruction."""
    for attempt in range(_MAX_JSON_ATTEMPTS):
        request_prompt = prompt if attempt == 0 else (
            "Your previous response was invalid. Return only valid JSON matching the requested structure.\n" + prompt
        )
        data = _parse_json(_generate(request_prompt, num_predict=num_predict))
        if data is not None and (validator is None or validator(data)):
            return data
    raise ValueError("Ollama returned invalid structured content after retry.")


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


def evaluate_answer(payload: dict):
    fallback = {
        "criteria_scores": {}, "strengths": [],
        "weaknesses": ["Automatic evaluation is unavailable."],
        "feedback": "Teacher review is recommended because local AI evaluation is unavailable.",
        "needs_teacher_review": True, "content_score": None,
    }
    if not _configured():
        fallback["error"] = "Local Ollama is not configured."
        return fallback
    rubric = payload.get("rubric") or {}
    criteria = rubric.get("criteria", []) if isinstance(rubric, dict) else []
    criteria = [item for item in criteria if isinstance(item, (str, dict))]
    criterion_names = [item if isinstance(item, str) else item.get("name") for item in criteria]
    criterion_names = [name for name in criterion_names if isinstance(name, str) and name.strip()]
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
        return fallback
    no_answer = transcript.casefold().strip(" .,!\t\n") in {"i don't know", "i do not know", "don't know", "do not know", "no idea"}
    if no_answer:
        names = criterion_names or ["Answer" ]
        return {
            "criteria_scores": {name: 0.0 for name in names},
            "criterion_details": {name: {"applicable": True, "explanation": "No answer provided.", "evidence": None} for name in names},
            "criteria_weights": criterion_weights or {name: 100.0 / len(names) for name in names},
            "content_score": 0.0, "strengths": [], "weaknesses": ["No answer was provided."],
            "missing_concepts": [], "correct_explanation": "Review the question's expected answer and try again.",
            "technical_accuracy": "Not answered", "feedback": "No answer was provided. Review the question and try again.", "needs_teacher_review": False,
        }

    prompt = (
        "Evaluate this candidate answer against the interview question, reference answer and rubric. Score only demonstrated correctness; "
        "confidence or fluent wording is not evidence of correctness. Scores are 0–10. Return JSON only with criteria_scores "
        "(criterion name to score), criterion_details (criterion name to {applicable:boolean, explanation:string, evidence:string|null}), "
        "technical_accuracy (brief string), missing_concepts (string array), correct_explanation (brief string), "
        "strengths (string array), weaknesses (string array), feedback (brief string), and needs_teacher_review (boolean). "
        "Do not invent evidence; any evidence must be an exact excerpt. Assess technical accuracy, conceptual understanding, relevance, completeness, "
        "problem solving and communication when applicable. Keep feedback concise.\n"
        f"Rubric: {json.dumps(criteria)}\nEvaluation input: {json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        data = _generate_json(prompt, num_predict=700, validator=lambda value: isinstance(value, dict) and
            isinstance(value.get("criteria_scores", value.get("criterion_scores")), dict) and isinstance(value.get("criterion_details", {}), dict))
        scores = data.get("criteria_scores", data.get("criterion_scores", {}))
        details = data.get("criterion_details", {})
        clean_scores, clean_details = {}, {}
        for name in criterion_names:
            detail = details.get(name, {})
            if not isinstance(detail, dict):
                detail = {}
            applicable = detail.get("applicable", True) is not False
            explanation = detail.get("explanation", "")
            evidence = detail.get("evidence")
            validated_evidence = None
            if isinstance(evidence, str) and evidence.strip() and len(evidence.strip()) <= 240:
                index = transcript.casefold().find(evidence.strip().casefold())
                if index >= 0:
                    validated_evidence = transcript[index:index + len(evidence.strip())]
            clean_details[name] = {"applicable": applicable, "explanation": explanation.strip()[:500] if isinstance(explanation, str) else "", "evidence": validated_evidence}
            if applicable:
                try:
                    value = float(scores[name])
                except (KeyError, TypeError, ValueError):
                    continue
                if math.isfinite(value) and 0 <= value <= 10:
                    clean_scores[name] = round(value, 2)
        applicable_count = sum(item["applicable"] for item in clean_details.values())
        if not criterion_names:
            # Preserve support for interviews whose rubric has no criteria.
            scores_values = [float(value) for value in scores.values() if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 10]
            if scores_values:
                clean_scores["Overall"] = round(sum(scores_values) / len(scores_values), 2)
                criterion_weights = {"Overall": 100.0}
        applicable_weight = sum(criterion_weights.get(name, 0) for name in clean_scores)
        content_score = round(sum(score * criterion_weights.get(name, 0) for name, score in clean_scores.items()) / applicable_weight, 2) if applicable_weight else None
        strengths, weaknesses = data.get("strengths", []), data.get("weaknesses", [])
        clean_strings = lambda values: [item.strip()[:300] for item in values if isinstance(item, str) and item.strip()][:10] if isinstance(values, list) else []
        feedback = data.get("feedback")
        correct_explanation = data.get("correct_explanation")
        technical_accuracy = data.get("technical_accuracy")
        return {
            **data, "criteria_scores": clean_scores, "criteria_weights": criterion_weights,
            "criterion_details": clean_details, "content_score": content_score,
            "strengths": clean_strings(strengths), "weaknesses": clean_strings(weaknesses),
            "missing_concepts": clean_strings(data.get("missing_concepts", [])),
            "correct_explanation": correct_explanation.strip()[:1200] if isinstance(correct_explanation, str) else "",
            "technical_accuracy": technical_accuracy.strip()[:300] if isinstance(technical_accuracy, str) else "",
            "feedback": feedback.strip()[:1000] if isinstance(feedback, str) else "",
            "needs_teacher_review": bool(data.get("needs_teacher_review", False)) or not applicable_count and bool(criterion_names) or bool(applicable_count and len(clean_scores) != applicable_count) or content_score is None,
        }
    except Exception as exc:
        logger.warning("AI answer evaluation failed error_type=%s", type(exc).__name__)
        fallback["error"] = _error_message(exc)
        return fallback


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
