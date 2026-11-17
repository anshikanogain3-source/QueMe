from io import BytesIO
from datetime import datetime
import hashlib
import json
import math
from statistics import mean
from xml.sax.saxutils import escape
from flask import current_app

from openpyxl import Workbook
from openpyxl.styles import Alignment
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from ..authz import score_weights
from ..extensions import db
from ..models import InterviewQuestion, Report
from .audio_analysis import combine_scores
from .llm import evaluate_answer

DUAL_EVALUATION_VERSION = 1
DUAL_SCORE_DISAGREEMENT_THRESHOLD = 2.0


def _concept_set(items):
    return {" ".join("".join(ch.lower() if ch.isalnum() else " " for ch in item).split()) for item in items if isinstance(item, str)}


def _compare_dual_evaluations(provider_results):
    ollama = provider_results.get("ollama", {})
    gemini = provider_results.get("gemini", {})
    successes = [item for item in (ollama, gemini) if item.get("status") == "SUCCESS" and isinstance(item.get("evaluation"), dict)]
    if len(successes) != 2:
        return {
            "status": "INCOMPLETE" if successes else "FAILED",
            "complete": False,
            "score_difference": None,
            "disagreements": [],
            "teacher_review_reasons": ["dual_evaluation_incomplete"],
        }
    left, right = ollama["evaluation"], gemini["evaluation"]
    if left.get("content_score") is None or right.get("content_score") is None:
        return {
            "status": "INCOMPLETE",
            "complete": False,
            "score_difference": None,
            "disagreements": ["insufficient_evaluation_evidence"],
            "teacher_review_reasons": ["insufficient_evaluation_evidence"],
        }
    reasons, disagreements = [], []
    if left.get("question_relevant") != right.get("question_relevant"):
        disagreements.append("relevance_disagreement")
        reasons.append("relevance_disagreement")
    if left.get("accuracy_category") != right.get("accuracy_category"):
        disagreements.append("classification_disagreement")
        reasons.append("classification_disagreement")
    if left.get("completeness") != right.get("completeness"):
        disagreements.append("completeness_disagreement")
        reasons.append("completeness_disagreement")
    left_score, right_score = left.get("content_score"), right.get("content_score")
    score_difference = round(abs(left_score - right_score), 2) if isinstance(left_score, (int, float)) and isinstance(right_score, (int, float)) else None
    if score_difference is None:
        disagreements.append("score_unavailable")
        reasons.append("insufficient_evaluation_evidence")
    elif score_difference >= DUAL_SCORE_DISAGREEMENT_THRESHOLD:
        disagreements.append("material_score_difference")
        reasons.append("material_score_difference")
    elif score_difference > 0:
        disagreements.append("minor_score_difference")
        reasons.append("minor_score_difference")
    # A score crossing an existing class boundary is material even when the gap is small.
    boundaries = (3, 7, 9)
    if score_difference is not None and any((left_score < boundary <= right_score) or (right_score < boundary <= left_score) for boundary in boundaries):
        disagreements.append("score_category_boundary")
        reasons.append("score_category_boundary")
    left_scores = left.get("criteria_scores", {}) if isinstance(left.get("criteria_scores"), dict) else {}
    right_scores = right.get("criteria_scores", {}) if isinstance(right.get("criteria_scores"), dict) else {}
    if set(left_scores) != set(right_scores):
        disagreements.append("rubric_criterion_mapping_disagreement")
        reasons.append("rubric_criterion_mapping_disagreement")
    criterion_conflicts = [name for name in left_scores.keys() & right_scores.keys()
                           if isinstance(left_scores[name], (int, float)) and isinstance(right_scores[name], (int, float))
                           and abs(left_scores[name] - right_scores[name]) >= DUAL_SCORE_DISAGREEMENT_THRESHOLD]
    if criterion_conflicts:
        disagreements.append("rubric_criterion_conflict")
        reasons.append("rubric_criterion_conflict:" + ", ".join(sorted(criterion_conflicts)))
    if _concept_set(left.get("missing_concepts", [])) != _concept_set(right.get("missing_concepts", [])):
        disagreements.append("missing_concept_disagreement")
        reasons.append("missing_concept_disagreement")
    if _concept_set(left.get("incorrect_claims", [])) != _concept_set(right.get("incorrect_claims", [])):
        disagreements.append("incorrect_claim_disagreement")
        reasons.append("incorrect_claim_disagreement")
    if _concept_set(left.get("correct_concepts", [])) != _concept_set(right.get("correct_concepts", [])):
        disagreements.append("correct_concept_disagreement")
        reasons.append("correct_concept_disagreement")
    left_details = left.get("criterion_details", {}) if isinstance(left.get("criterion_details"), dict) else {}
    right_details = right.get("criterion_details", {}) if isinstance(right.get("criterion_details"), dict) else {}
    evidence_conflicts = [name for name in left_details.keys() & right_details.keys()
                          if left_details[name].get("evidence") != right_details[name].get("evidence")]
    if evidence_conflicts:
        disagreements.append("evidence_excerpt_disagreement")
        reasons.append("evidence_excerpt_disagreement")
    if _concept_set(left.get("suggested_improvements", [])) != _concept_set(right.get("suggested_improvements", [])):
        disagreements.append("suggested_improvement_disagreement")
        reasons.append("suggested_improvement_disagreement")
    for evaluation in (left, right):
        scores = evaluation.get("criteria_scores", {})
        details = evaluation.get("criterion_details", {})
        if any(score > 0 and (
            not isinstance(details.get(name), dict)
            or not details[name].get("evidence")
            or details[name].get("evidence_supports_claim") is not True
        ) for name, score in scores.items() if isinstance(score, (int, float))):
            disagreements.append("unsupported_positive_evidence")
            reasons.append("unsupported_positive_evidence")
            break
        if evaluation.get("completeness") == "SUBSTANTIALLY_INCORRECT":
            reasons.append("substantially_incorrect_answer")
    if left.get("needs_teacher_review") or right.get("needs_teacher_review"):
        reasons.append("provider_review_required")
    if any(isinstance(score, (int, float)) and score > 0 for item in (left, right)
           for score in (item.get("criteria_scores", {}) or {}).values()):
        reasons.append("positive_score_teacher_review_required")
    if not left.get("question_relevant") or not right.get("question_relevant"):
        reasons.append("answer_not_relevant")
    material = any(reason in {
        "relevance_disagreement", "classification_disagreement", "material_score_difference",
        "completeness_disagreement", "score_category_boundary", "rubric_criterion_conflict",
        "rubric_criterion_mapping_disagreement", "missing_concept_disagreement",
        "incorrect_claim_disagreement", "correct_concept_disagreement", "unsupported_positive_evidence",
        "substantially_incorrect_answer",
    } or reason.startswith("rubric_criterion_conflict:") for reason in reasons)
    status = "MATERIAL_DISAGREEMENT" if material else "MINOR_DISAGREEMENT" if disagreements else "AGREEMENT"
    return {
        "status": status,
        "complete": True,
        "score_difference": score_difference,
        "disagreements": sorted(set(disagreements)),
        "teacher_review_reasons": sorted(set(reasons)),
        "criterion_conflicts": sorted(criterion_conflicts),
    }

AI_DECISION_SUPPORT_DISCLAIMER = (
    "QueMe's AI feedback is decision support for practice and learning. "
    "It is not a final placement decision and should be considered alongside teacher review."
)


def evaluate_interview_answer(question, *, correlation_id=None):
    """Score one usable answer, retaining an explicit review state on fallback."""
    analysis = question.analysis
    transcript = (analysis.transcript if analysis else "") or ""
    rubric = question.rubric
    rubric_data = rubric.criteria_json if rubric and isinstance(rubric.criteria_json, dict) else {}
    criteria = rubric_data.get("criteria", []) if isinstance(rubric_data, dict) else []
    needs_review = not transcript or not analysis or analysis.transcription_status != "OK"
    evaluation = {
        "criteria_scores": {},
        "content_score": None,
        "strengths": [],
        "weaknesses": [],
        "feedback": "Transcript unavailable; teacher review is required." if needs_review else "",
        "needs_teacher_review": needs_review,
    }
    if transcript:
        evaluation_payload = {
            "question": question.question.question_text if question.question else (question.followup_text or ""),
            "question_type": question.question.question_type if question.question else "",
            "expected_key_points": question.question.expected_key_points if question.question else "",
            "reference_answer": question.question.reference_answer if question.question else "",
            "transcript": transcript,
            "audio_metrics": {
                key: analysis.to_dict()[key]
                for key in (
                    "answer_duration_seconds", "speaking_duration_seconds", "words_per_minute",
                    "pause_count", "total_pause_duration_seconds", "longest_pause_seconds",
                    "filler_word_count", "filler_word_rate", "repetition_count", "speech_ratio",
                    "audio_quality_status",
                )
            },
            "rubric": {
                "name": rubric.rubric_name if rubric else "General interview rubric",
                "maximum_score": rubric.maximum_score if rubric else 10,
                "criteria": criteria,
            },
        }
        if current_app.config.get("EVALUATION_MODE", "dual_sequential") == "dual_sequential":
            old_json = question.evaluation_json if isinstance(question.evaluation_json, dict) else {}
            saved = old_json.get("dual_model") if isinstance(old_json.get("dual_model"), dict) else {}
            providers = dict(saved.get("providers", {})) if saved.get("version") == DUAL_EVALUATION_VERSION else {}
            for provider in ("ollama", "gemini"):
                prior = providers.get(provider, {})
                # Successful output is durable across worker retries. Permanent failures are final too.
                if prior.get("status") == "SUCCESS" or (prior.get("status") == "FAILED" and not prior.get("retryable")):
                    continue
                provider_result = evaluate_answer(
                    evaluation_payload,
                    correlation_id=correlation_id,
                    provider_override=provider,
                )
                attempt = provider_result.pop("provider_attempt", {})
                count = int(prior.get("attempt_count", 0)) + int(attempt.get("attempt_count", 0))
                providers[provider] = {
                    "provider": provider,
                    "model": attempt.get("model"),
                    "status": attempt.get("status", "FAILED"),
                    "duration_ms": int(prior.get("duration_ms", 0)) + int(attempt.get("duration_ms", 0)),
                    "attempt_count": count,
                    "error_category": attempt.get("error_category"),
                    "retryable": bool(attempt.get("retryable")),
                    "evaluation": {key: value for key, value in provider_result.items() if key not in ("retryable", "error_category")}
                    if attempt.get("status") == "SUCCESS" else None,
                }
                # Commit each provider independently so a worker interruption cannot erase its result.
                question.evaluation_json = {**old_json, "dual_model": {
                    "version": DUAL_EVALUATION_VERSION,
                    "providers": providers,
                    "comparison": {"status": "INCOMPLETE", "complete": False, "teacher_review_reasons": ["comparison_pending"]},
                }}
                db.session.commit()
            comparison = _compare_dual_evaluations(providers)
            left = providers.get("ollama", {}).get("evaluation") or {}
            right = providers.get("gemini", {}).get("evaluation") or {}
            same_score = (
                comparison.get("complete")
                and left.get("content_score") is not None
                and left.get("content_score") == right.get("content_score")
            )
            if comparison.get("status") == "AGREEMENT" and same_score:
                evaluation = dict(left)
            else:
                evaluation = {
                    "criteria_scores": {}, "criterion_details": {}, "content_score": None,
                    "evaluation_status": "UNAVAILABLE", "feedback": "",
                    "strengths": [], "weaknesses": [], "missing_concepts": [],
                }
            needs_review = needs_review or comparison.get("status") != "AGREEMENT" or bool(comparison.get("teacher_review_reasons"))
            needs_review = needs_review or bool(left.get("needs_teacher_review")) or bool(right.get("needs_teacher_review"))
            evaluation["dual_model"] = {
                "version": DUAL_EVALUATION_VERSION,
                "providers": providers,
                "comparison": comparison,
                "decision": "TEACHER_REVIEW" if needs_review else "PROVISIONAL_AGREEMENT",
                "needs_teacher_review": needs_review,
                "retryable": any(item.get("status") == "FAILED" and item.get("retryable") for item in providers.values()),
            }
            if evaluation["dual_model"]["retryable"]:
                evaluation["error"] = "A transient provider failure is pending a bounded retry."
                evaluation["retryable"] = True
            evaluation["needs_teacher_review"] = needs_review
        else:
            provider = current_app.config.get("EVALUATION_PROVIDER", "ollama")
            evaluation = evaluate_answer(
                evaluation_payload,
                correlation_id=correlation_id,
                provider_override=provider,
            )
            needs_review = needs_review or bool(evaluation.get("needs_teacher_review"))
    rubric_snapshot = {
        "rubric_id": rubric.rubric_id if rubric else None,
        "name": rubric.rubric_name if rubric else "General interview rubric",
        "maximum_score": rubric.maximum_score if rubric else 10,
        "criteria": criteria,
    }
    evaluation["rubric_version"] = hashlib.sha256(
        json.dumps(rubric_snapshot, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()[:16]
    evaluation["rubric_snapshot"] = rubric_snapshot
    evaluation["evaluation_status"] = "COMPLETED" if evaluation.get("content_score") is not None else "UNAVAILABLE"

    delivery_score = float(analysis.delivery_score) if analysis and analysis.delivery_score is not None else None
    raw_content = evaluation.get("content_score")
    content_score = _valid_score(raw_content)
    question.transcript = transcript
    question.content_score = content_score
    question.delivery_score = delivery_score
    question.final_ai_score = None
    if content_score is not None and delivery_score is not None:
        content_weight, delivery_weight = score_weights()
        evaluation["score_weights"] = {
            "content_weight": content_weight,
            "delivery_weight": delivery_weight,
        }
        if evaluation.get("accuracy_category") == "INCORRECT_OR_IRRELEVANT":
            question.final_ai_score = content_score
        else:
            question.final_ai_score = combine_scores(content_score, delivery_score, content_weight, delivery_weight)
    prior_reviews = getattr(question, "reviews", ()) or ()
    teacher_has_reviewed = bool(getattr(question, "teacher_score", None) is not None or getattr(question, "teacher_remark", None)) or any(
        item.teacher_score is not None or item.teacher_remark or item.teacher_criteria_json
        for item in prior_reviews
    )
    question.needs_review = False if teacher_has_reviewed else needs_review
    question.evaluation_json = evaluation
    return evaluation


def generate_interview_report(interview):
    """Create or refresh the report after completion; safe to call more than once."""
    questions = InterviewQuestion.query.filter_by(interview_id=interview.interview_id).all()
    ai_scores = [score for q in questions if (score := _valid_score(q.final_ai_score)) is not None]
    reviewed_scores = [
        score
        for q in questions
        if (score := _valid_score(q.teacher_score if q.teacher_score is not None else q.final_ai_score)) is not None
    ]
    report = Report.query.filter_by(interview_id=interview.interview_id).first()
    if report is None:
        report = Report(interview_id=interview.interview_id)
        db.session.add(report)
    report.ai_final_score = round(mean(ai_scores), 2) if ai_scores else None
    report.final_score = (
        float(report.teacher_score)
        if report.teacher_score is not None
        else round(mean(reviewed_scores), 2) if reviewed_scores else None
    )
    if report.teacher_score is not None or any(q.teacher_score is not None for q in questions):
        report.score_source = "TEACHER"
    elif report.ai_final_score is not None:
        report.score_source = "AI_DUAL_AUDIO" if any(
            isinstance(q.evaluation_json, dict) and isinstance(q.evaluation_json.get("dual_model"), dict)
            for q in questions
        ) else "AI_AUDIO"
    else:
        report.score_source = "NEEDS_REVIEW"
    if report.reviewed_at:
        report.report_status = "REVIEWED"
    elif any(q.needs_review for q in questions) or report.final_score is None:
        report.report_status = "NEEDS_REVIEW"
    else:
        report.report_status = "READY"
    if report.generated_at is None:
        report.generated_at = datetime.utcnow()
    interview.final_score = report.final_score
    return report


def summarize_interview_audio(questions):
    """Summarize saved usable recordings, retaining per-metric sample counts."""
    from .audio_analysis import tokenize

    metrics = (
        "words_per_minute", "pause_count", "total_pause_duration_seconds",
        "longest_pause_seconds", "filler_word_count", "delivery_score",
    )
    recordings = [question.analysis for question in questions if _usable_recording(question)]
    summary = {
        "questions_included": len(recordings),
        "averages": {},
        "metric_sample_counts": {},
    }
    for field in metrics:
        values = []
        for analysis in recordings:
            raw_value = getattr(analysis, field, None)
            if raw_value is None:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(value) or value < 0 or (field == "delivery_score" and value > 10):
                continue
            values.append(value)
        summary[field] = round(mean(values), 2) if values else None
        summary["averages"][field] = summary[field]
        summary["metric_sample_counts"][field] = len(values)
    filler_totals = []
    for analysis in recordings:
        words = len(tokenize(analysis.transcript or ""))
        try:
            count = int(getattr(analysis, "filler_word_count", None))
        except (TypeError, ValueError, OverflowError):
            continue
        raw_count = getattr(analysis, "filler_word_count", None)
        if words and count >= 0 and count <= words and float(count) == float(raw_count):
            filler_totals.append((count, words))
    filler_words = sum(count for count, _ in filler_totals)
    spoken_words = sum(count for _, count in filler_totals)
    per_100 = (filler_words / spoken_words * 100) if spoken_words else None
    summary["fillers_per_100_words"] = round(per_100, 2) if per_100 is not None else None
    summary["averages"]["fillers_per_100_words"] = summary["fillers_per_100_words"]
    summary["metric_sample_counts"]["fillers_per_100_words"] = len(filler_totals)
    summary["filler_word_denominator"] = spoken_words
    return summary


def build_analysis_coverage(questions):
    total = len(questions)
    attempted = [
        question for question in questions
        if question.asked_at or question.answer_audio_path or (question.transcript or "").strip()
    ]
    recordings = [question for question in questions if question.answer_audio_path]
    usable = [
        question for question in recordings
        if _usable_recording(question)
    ]
    transcribed = [
        question for question in questions
        if question.analysis is not None
        and question.analysis.transcription_status == "OK"
        and bool((question.analysis.transcript or "").strip())
    ]
    content_evaluated = [question for question in attempted if _valid_score(question.content_score) is not None]
    communication_analyzed = [
        question for question in usable
        if _valid_score(question.analysis.delivery_score) is not None
    ]

    def coverage(count, denominator):
        return {
            "count": count,
            "denominator": denominator,
            "percentage": round(count / denominator * 100, 1) if denominator else None,
        }

    fully_analyzed = sum(
        question in transcribed and question in content_evaluated and question in communication_analyzed
        for question in attempted
    )
    return {
        "total_questions": total,
        "attempted_questions": len(attempted),
        "questions_answered": len(recordings),
        "questions_with_recordings": len(recordings),
        "usable_recordings": len(usable),
        "transcribed_answers": len(transcribed),
        "content_evaluations": len(content_evaluated),
        "communication_analyses": len(communication_analyzed),
        "failed_or_unavailable_analyses": sum(
            question not in content_evaluated or question not in communication_analyzed or question not in transcribed
            for question in attempted
        ),
        "coverage": {
            "transcription": coverage(len(transcribed), len(attempted)),
            "content_evaluation": coverage(len(content_evaluated), len(attempted)),
            "communication_analysis": coverage(len(communication_analyzed), len(attempted)),
            "overall": coverage(fully_analyzed, len(attempted)),
        },
        "status": "COMPLETE" if attempted and fully_analyzed == len(attempted) else (
            "PARTIALLY_ANALYZED" if attempted else "INSUFFICIENT_DATA"
        ),
    }


def question_analysis_status(question):
    if not question.asked_at and not question.answer_audio_path and not (question.transcript or "").strip():
        return {"status": "NOT_ATTEMPTED", "reason": "This question was not attempted."}
    if not question.answer_audio_path:
        return {"status": "AUDIO_UNAVAILABLE", "reason": "No saved answer recording is available."}
    analysis = question.analysis
    if analysis is None:
        return {"status": "ANALYSIS_UNAVAILABLE", "reason": "No audio analysis record is available."}
    if analysis.transcription_status != "OK" or not (analysis.transcript or "").strip():
        return {"status": "TRANSCRIPT_UNAVAILABLE", "reason": "The answer could not be transcribed."}
    if analysis.audio_usable is not True or analysis.audio_quality_status != "OK":
        return {"status": "INSUFFICIENT_AUDIO", "reason": "The recording did not meet audio quality checks."}
    evaluation = question.evaluation_json if isinstance(question.evaluation_json, dict) else {}
    if _valid_score(question.content_score) is None:
        reason = evaluation.get("error") or "Content evaluation did not produce a valid score."
        return {"status": "EVALUATION_FAILED", "reason": str(reason)[:300]}
    if _valid_score(analysis.delivery_score) is None:
        return {"status": "COMMUNICATION_ANALYSIS_UNAVAILABLE", "reason": "Communication metrics are incomplete."}
    return {"status": "COMPLETE", "reason": None}


def answer_processing_status(question):
    job = question.processing_job
    if job is None:
        if question.answer_audio_path:
            return "PENDING"
        return "TEACHER_REVIEW" if question.needs_review else "NOT_APPLICABLE"
    if job.status in ("QUEUED", "PROCESSING"):
        return "PENDING"
    if job.status == "RETRY_WAIT":
        return "RETRYABLE_FAILURE"
    if job.status == "NEEDS_REVIEW" or job.outcome == "TEACHER_REVIEW":
        return "TEACHER_REVIEW"
    if job.status == "COMPLETED" and job.outcome == "EVALUATED":
        return "SUCCESSFULLY_EVALUATED"
    return "TEACHER_REVIEW"


def _valid_score(value):
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return score if math.isfinite(score) and 0 <= score <= 10 else None


def _usable_recording(question):
    analysis = question.analysis
    return bool(
        question.answer_audio_path
        and analysis is not None
        and analysis.audio_usable is True
        and analysis.audio_quality_status == "OK"
    )


def _validated_evidence(detail, transcript):
    excerpt = detail.get("evidence") if isinstance(detail, dict) else None
    if not isinstance(excerpt, str) or not excerpt.strip() or len(excerpt.strip()) > 240:
        return None
    start = transcript.casefold().find(excerpt.strip().casefold())
    return transcript[start : start + len(excerpt.strip())] if start >= 0 else None


def build_topic_analysis(questions):
    groups = {}
    for question in questions:
        question_bank_row = question.question
        topics = question_bank_row.topics_json if question_bank_row else []
        if not isinstance(topics, list):
            continue
        for topic in topics:
            if isinstance(topic, str) and topic.strip():
                groups.setdefault(topic.strip(), []).append(question)
    output = []
    for topic, rows in sorted(groups.items(), key=lambda item: item[0].casefold()):
        scored = [(row, _valid_score(row.content_score)) for row in rows]
        scored = [(row, score) for row, score in scored if score is not None]
        average = round(mean(score for _, score in scored), 2) if scored else None
        output.append({
            "topic": topic,
            "average_content_score": average,
            "questions_scored": len(scored),
            "questions_total": len(rows),
            "question_orders": [row.question_order for row in rows],
            "sample_note": "Based on one question; treat as an early signal." if len(scored) == 1 else None,
            "classification": (
                "INSUFFICIENT_DATA" if average is None else
                "STRENGTH" if average >= 7 else "REVISION_AREA" if average < 6 else "DEVELOPING"
            ),
        })
    return output


def build_improvement_plan(questions, topic_analysis, audio_summary):
    candidates = []
    for question in questions:
        evaluation = question.evaluation_json if isinstance(question.evaluation_json, dict) else {}
        details = evaluation.get("criterion_details", {})
        scores = evaluation.get("criteria_scores", {})
        if not isinstance(details, dict) or not isinstance(scores, dict):
            continue
        transcript = (question.transcript or (question.analysis.transcript if question.analysis else "") or "")
        for criterion, raw_score in scores.items():
            score = _valid_score(raw_score)
            if score is None or score >= 7:
                continue
            detail = details.get(criterion, {})
            if not isinstance(detail, dict) or detail.get("applicable") is False:
                continue
            evidence = _validated_evidence(detail, transcript)
            candidates.append({
                "priority": 0,
                "area": criterion,
                "question_order": question.question_order,
                "topic": (question.question.topics_json or [None])[0] if question.question else None,
                "score": score,
                "evidence": evidence,
                "interpretation": detail.get("explanation") or f"The rubric score for {criterion} was {score:.1f}/10.",
                "practice_activity": f"Re-answer question {question.question_order} with a clearer focus on {criterion.lower()}.",
                "measurable_target": f"Aim for at least 7/10 on {criterion} in a new practice answer.",
                "review_timeframe": "Before your next interview practice.",
            })

    for topic in topic_analysis:
        score = topic["average_content_score"]
        if topic["classification"] != "REVISION_AREA":
            continue
        candidates.append({
            "priority": 1,
            "area": topic["topic"],
            "topic": topic["topic"],
            "question_orders": topic["question_orders"],
            "score": score,
            "evidence": None,
            "interpretation": f"The average content score for this tagged topic was {score:.1f}/10 across {topic['questions_scored']} scored question(s).",
            "practice_activity": f"Review the concepts asked in questions {', '.join(map(str, topic['question_orders']))}, then explain one concept aloud.",
            "measurable_target": "Reach at least 6/10 on a new question tagged with this topic.",
            "review_timeframe": "Before your next interview practice.",
        })

    if audio_summary.get("fillers_per_100_words") is not None and audio_summary["fillers_per_100_words"] > 5:
        rate = audio_summary["fillers_per_100_words"]
        candidates.append({
            "priority": 2,
            "area": "Filler words",
            "topic": None,
            "score": None,
            "evidence": f"{rate:.1f} filler words per 100 spoken words across {audio_summary['filler_word_denominator']} words.",
            "interpretation": "The recorded answers contained frequent filler words.",
            "practice_activity": "Record a 60-second answer and pause briefly instead of filling thinking time.",
            "measurable_target": f"Reduce the next practice rate below {rate:.1f} per 100 words.",
            "review_timeframe": "At your next short practice session.",
        })
    candidates.sort(key=lambda item: (item["priority"], item["score"] if item["score"] is not None else 0))
    deduplicated = []
    seen_areas = set()
    for candidate in candidates:
        normalized_area = " ".join(str(candidate.get("area") or "").casefold().split())
        if normalized_area in seen_areas:
            continue
        seen_areas.add(normalized_area)
        deduplicated.append(candidate)
        if len(deduplicated) == 3:
            break
    return deduplicated


def build_report_analytics(questions):
    audio_summary = summarize_interview_audio(questions)
    coverage = build_analysis_coverage(questions)
    topics = build_topic_analysis(questions)
    content = [_valid_score(question.content_score) for question in questions]
    content = [score for score in content if score is not None]
    delivery = [_valid_score(question.delivery_score) for question in questions]
    delivery = [score for score in delivery if score is not None]
    return {
        "score_summary": {
            "content_score": round(mean(content), 2) if content else None,
            "content_score_count": len(content),
            "delivery_score": round(mean(delivery), 2) if delivery else None,
            "delivery_score_count": len(delivery),
        },
        "audio_summary": audio_summary,
        "analysis_coverage": coverage,
        "topic_analysis": topics,
        "improvement_plan": build_improvement_plan(questions, topics, audio_summary),
    }


def get_interview_score_weights(questions):
    content_weight, delivery_weight = score_weights()
    for question in questions:
        evaluation = question.evaluation_json if isinstance(question.evaluation_json, dict) else {}
        stored = evaluation.get("score_weights")
        if not isinstance(stored, dict):
            continue
        content = stored.get("content_weight")
        delivery = stored.get("delivery_weight")
        if (
            isinstance(content, (int, float)) and math.isfinite(content)
            and isinstance(delivery, (int, float)) and math.isfinite(delivery)
            and 0 <= content <= 1 and 0 <= delivery <= 1
            and math.isclose(content + delivery, 1.0, abs_tol=1e-6)
        ):
            return content, delivery
    return content_weight, delivery_weight


def build_pdf(interview, questions, report):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm)
    styles = getSampleStyleSheet()
    analytics = build_report_analytics(questions)
    audio = analytics["audio_summary"]
    coverage = analytics["analysis_coverage"]
    content_weight, delivery_weight = get_interview_score_weights(questions)
    score_summary = analytics["score_summary"]

    def audio_value(key, unit=""):
        value = audio.get(key)
        if value is None:
            return "Not available"
        count = audio["metric_sample_counts"].get(key, 0)
        return f"{value:.1f}{unit} ({count} answers)"

    story = [
        Paragraph("QueMe Interview Report", styles["Title"]),
        Paragraph(escape(AI_DECISION_SUPPORT_DISCLAIMER), styles["Italic"]),
        Spacer(1, 12),
        Paragraph(f"Student: {escape(interview.student.full_name if interview.student else '-')}", styles["Normal"]),
        Paragraph(f"Interview: {escape(interview.template.title if interview.template else '-')}", styles["Normal"]),
        Paragraph(f"Status: {interview.status}", styles["Normal"]),
        Paragraph(f"Overall score: {report.final_score if report else interview.final_score}", styles["Normal"]),
        Paragraph(f"Score source: {escape(report.score_source if report and report.score_source else 'AI + Audio Analysis')}", styles["Normal"]),
        Paragraph(f"Report status: {escape(report.report_status if report and report.report_status else 'NEEDS_REVIEW')}", styles["Normal"]),
        Paragraph(
            "Answer processing: "
            f"{sum(answer_processing_status(q) == 'SUCCESSFULLY_EVALUATED' for q in questions)} successfully evaluated · "
            f"{sum(answer_processing_status(q) == 'PENDING' for q in questions)} pending · "
            f"{sum(answer_processing_status(q) == 'RETRYABLE_FAILURE' for q in questions)} retryable failures · "
            f"{sum(answer_processing_status(q) == 'TEACHER_REVIEW' for q in questions)} require teacher review. "
            "Missing evaluations are not assigned a zero score.",
            styles["Normal"],
        ),
        Paragraph(
            f"Score method: question final AI score = content × {content_weight * 100:.0f}% + "
            f"delivery × {delivery_weight * 100:.0f}%; both component scores use a 0–10 scale.",
            styles["Normal"],
        ),
        Spacer(1, 12),
        Paragraph(
            "Interview score averages: "
            f"content {score_summary['content_score'] if score_summary['content_score'] is not None else 'Not available'}/10 "
            f"({score_summary['content_score_count']} answers) · "
            f"delivery {score_summary['delivery_score'] if score_summary['delivery_score'] is not None else 'Not available'}/10 "
            f"({score_summary['delivery_score_count']} answers).",
            styles["Normal"],
        ),
    ]
    story.extend([
        Paragraph("Communication analytics", styles["Heading2"]),
        Paragraph(
            f"Usable recordings: {audio['questions_included']} · "
            f"Average speaking rate: {audio_value('words_per_minute', ' WPM')} "
            f"({audio['metric_sample_counts']['words_per_minute']} answers) · "
            f"Pause count: {audio_value('pause_count')} per answer · "
            f"Pause duration: {audio_value('total_pause_duration_seconds', ' sec')} per answer · "
            f"Longest pause: {audio_value('longest_pause_seconds', ' sec')} per answer · "
            f"Fillers: {audio_value('fillers_per_100_words')} per 100 words "
            f"({audio['filler_word_denominator']} words) · "
            f"Delivery: {audio_value('delivery_score', '/10')}.",
            styles["Normal"],
        ),
        Paragraph(
            f"Coverage: {coverage['status'].replace('_', ' ').lower()} · "
            f"{coverage['questions_answered']} recordings / {coverage['total_questions']} questions · "
            f"{coverage['usable_recordings']} usable · {coverage['transcribed_answers']} transcribed · "
            f"{coverage['content_evaluations']} content evaluations · "
            f"{coverage['communication_analyses']} communication analyses.",
            styles["Normal"],
        ),
        Paragraph(
            "Coverage rates: " + " · ".join(
                f"{name.replace('_', ' ')} "
                f"{values['percentage'] if values['percentage'] is not None else 'Not available'}% "
                f"({values['count']}/{values['denominator']})"
                for name, values in coverage["coverage"].items()
            ),
            styles["Normal"],
        ),
        Spacer(1, 8),
    ])
    story.append(Paragraph("Topic performance", styles["Heading2"]))
    if analytics["topic_analysis"]:
        for topic in analytics["topic_analysis"]:
            value = f"{topic['average_content_score']:.1f}/10" if topic["average_content_score"] is not None else "Not available"
            story.append(Paragraph(
                f"{escape(topic['topic'])}: {value} · {topic['questions_scored']}/{topic['questions_total']} scored · "
                f"{topic['classification'].replace('_', ' ').lower()} · Questions {escape(', '.join(map(str, topic['question_orders'])))}"
                + (f" · {escape(topic['sample_note'])}" if topic["sample_note"] else ""),
                styles["Normal"],
            ))
    else:
        story.append(Paragraph("Not available; questions have no topic tags.", styles["Normal"]))
    story.append(Paragraph("Personalized practice plan", styles["Heading2"]))
    if analytics["improvement_plan"]:
        for item in analytics["improvement_plan"]:
            story.append(Paragraph(
                f"{escape(item['area'])}: {escape(item['interpretation'])} "
                f"Practice: {escape(item['practice_activity'])} "
                f"Target: {escape(item['measurable_target'])} · {escape(item['review_timeframe'])}"
                + (f" Evidence: {escape(item['evidence'])}" if item.get("evidence") else ""),
                styles["Normal"],
            ))
    else:
        story.append(Paragraph("Not available; there is not enough evaluated evidence to set a practice priority.", styles["Normal"]))
    story.append(Spacer(1, 8))
    for q in questions:
        label = "Follow-up" if q.is_followup else f"Question {q.question_order}"
        question_text = q.question.question_text if q.question else (q.followup_text or "")
        story.append(Paragraph(f"{label}: {escape(question_text)}", styles["Heading3"]))
        story.append(Paragraph(f"Transcript: {escape(q.transcript or '—')}", styles["Normal"]))
        story.append(Paragraph(f"Processing status: {answer_processing_status(q).replace('_', ' ').lower()}", styles["Normal"]))
        story.append(
            Paragraph(
                f"Content {q.content_score}/10 · Delivery {q.delivery_score}/10 · Final AI {q.final_ai_score}/10 · "
                f"Teacher score {q.teacher_score if q.teacher_score is not None else '—'}/10",
                styles["Normal"],
            )
        )
        if q.analysis:
            def question_metric(field):
                value = getattr(q.analysis, field)
                return str(value) if value is not None else "—"

            story.append(Paragraph(
                f"Audio quality: {escape(q.analysis.audio_quality_status or 'unknown')} · "
                f"Words/min: {question_metric('words_per_minute')} · Pauses: {question_metric('pause_count')} · "
                f"Fillers: {question_metric('filler_word_count')}",
                styles["Normal"],
            ))
        ev = q.evaluation_json or {}
        dual = ev.get("dual_model") if isinstance(ev, dict) else None
        if dual:
            comparison = dual.get("comparison", {})
            story.append(Paragraph(
                f"Dual-model comparison: {escape(str(comparison.get('status', 'PENDING')))} · "
                f"score difference {escape(str(comparison.get('score_difference', 'unavailable')))} · "
                f"teacher review {'required' if dual.get('needs_teacher_review') else 'not required'}.",
                styles["Normal"],
            ))
            for provider_name in ("ollama", "gemini"):
                provider = dual.get("providers", {}).get(provider_name, {})
                model = provider.get("evaluation") or {}
                story.append(Paragraph(
                    f"{escape(provider_name.title())} ({escape(str(provider.get('model') or 'unknown model'))}): "
                    f"{escape(str(provider.get('status', 'not run')))} · score "
                    f"{escape(str(model.get('content_score', 'unavailable')))} · "
                    f"{escape(str(model.get('accuracy_category', 'unavailable')))}.",
                    styles["Normal"],
                ))
                if model.get("feedback") and model.get("evaluation_status") != "UNAVAILABLE":
                    story.append(Paragraph(f"{escape(provider_name.title())} feedback: {escape(str(model['feedback']))}", styles["Normal"]))
                if model.get("missing_concepts"):
                    story.append(Paragraph(f"{escape(provider_name.title())} missing concepts: {escape(', '.join(model['missing_concepts']))}", styles["Normal"]))
                details = model.get("criterion_details", {})
                if isinstance(details, dict):
                    for criterion, detail in details.items():
                        if isinstance(detail, dict):
                            evidence = detail.get("evidence") or "unavailable"
                            story.append(Paragraph(
                                f"{escape(provider_name.title())} {escape(str(criterion))} evidence: {escape(str(evidence))} · "
                                f"{escape(str(detail.get('evidence_explanation') or ''))}", styles["Normal"],
                            ))
        elif ev.get("feedback") and ev.get("evaluation_status") != "UNAVAILABLE" and (
            ev.get("provider_attempt", {}).get("status") == "SUCCESS" or ev.get("content_score") is not None
        ):
            story.append(Paragraph(f"AI summary: {escape(str(ev.get('feedback')))}", styles["Normal"]))
        criterion_scores = ev.get("criteria_scores", {}) if isinstance(ev, dict) else {}
        criterion_details = ev.get("criterion_details", {}) if isinstance(ev, dict) else {}
        if isinstance(criterion_scores, dict):
            for criterion, score in criterion_scores.items():
                detail = criterion_details.get(criterion, {}) if isinstance(criterion_details, dict) else {}
                story.append(Paragraph(
                    f"{escape(str(criterion))}: {score}/10. "
                    f"AI interpretation: {escape(str(detail.get('explanation') or 'Not available.'))}. "
                    f"Transcript evidence: {escape(str(detail.get('evidence') or 'Not available.'))}",
                    styles["Normal"],
                ))
        if q.reviews:
            review = q.reviews[-1]
            if review.teacher_score is not None:
                story.append(Paragraph(
                    f"Teacher comparison: AI {review.ai_score if review.ai_score is not None else '—'}/10 · "
                    f"Teacher {review.teacher_score}/10 · reviewed {review.reviewed_at.isoformat() if review.reviewed_at else 'date unavailable'}.",
                    styles["Normal"],
                ))
        if q.teacher_remark:
            story.append(Paragraph(f"Teacher remark: {escape(q.teacher_remark)}", styles["Normal"]))
        story.append(Spacer(1, 8))
    if report and report.teacher_remark:
        story.append(Paragraph(f"Teacher remarks: {escape(report.teacher_remark)}", styles["Heading3"]))
    doc.build(story)
    buf.seek(0)
    return buf


def build_excel(rows, title="QueMe Reports", summary=None):
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    guidance = wb.create_sheet("Guidance")
    guidance.append([AI_DECISION_SUPPORT_DISCLAIMER])
    guidance.column_dimensions["A"].width = 110
    guidance["A1"].alignment = Alignment(wrap_text=True, vertical="top")
    guidance.row_dimensions[1].height = 42
    if summary:
        summary_ws = wb.create_sheet("Interview Analytics")
        summary_ws.append(["Metric", "Value", "Included sample"])
        for key, value in summary.items():
            if isinstance(value, dict) and {"value", "count"} <= set(value):
                summary_ws.append([key, value["value"], value["count"]])
            else:
                summary_ws.append([key, value, ""])
        summary_ws.column_dimensions["A"].width = 40
        summary_ws.column_dimensions["B"].width = 32
        summary_ws.column_dimensions["C"].width = 22
    if not rows:
        ws.append(["No data"])
    else:
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            values = []
            for header in headers:
                value = row.get(header)
                if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
                    value = "'" + value
                values.append(value)
            ws.append(values)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
