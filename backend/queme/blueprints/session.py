from datetime import datetime
import math
from pathlib import Path
from random import sample
import uuid

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from ..api_errors import api_error, json_object
from ..authz import login_required
from ..extensions import db
from ..models import AnswerProcessingJob, AudioAnalysis, Interview, InterviewQuestion
from ..services.answer_jobs import enqueue_answer, latest_completed_evaluation, processing_summary
from ..services.storage import get_storage

bp = Blueprint("session", __name__)

ALLOWED_AUDIO_TYPES = {
    "audio/webm": ".webm",
    "video/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
}
def _student_interview(interview_id):
    interview = Interview.query.filter_by(interview_id=interview_id, student_id=g.user.user_id).first()
    return interview


@bp.get("/rapidfire/questions")
@login_required("student")
def rapidfire_questions():
    """Return a small set of this student's assigned questions for informal practice."""
    rows = (
        InterviewQuestion.query.join(Interview)
        .filter(
            Interview.student_id == g.user.user_id,
            InterviewQuestion.question_id.isnot(None),
        )
        .all()
    )
    questions = {}
    for row in rows:
        question = row.question
        if question is not None:
            questions[question.question_id] = {
                "question_id": question.question_id,
                "question_text": question.question_text,
                "question_type": question.question_type,
                "difficulty": question.difficulty,
            }
    choices = list(questions.values())
    return jsonify(sample(choices, min(5, len(choices))) if choices else [])


def _session_payload(interview):
    questions = sorted(interview.questions, key=lambda row: row.question_order)
    total = len(questions)
    index = min(max(interview.current_index or 0, 0), total)
    current = questions[index] if interview.status == "IN_PROGRESS" and index < total else None
    return {
        "interview_id": interview.interview_id,
        "template_id": interview.template_id,
        "template_title": interview.template.title if interview.template else "Interview",
        "teacher_name": interview.teacher.full_name if interview.teacher else None,
        "status": interview.status,
        "scheduled_at": interview.scheduled_at.isoformat() if interview.scheduled_at else None,
        "started_at": interview.started_at.isoformat() if interview.started_at else None,
        "ended_at": interview.ended_at.isoformat() if interview.ended_at else None,
        "consent_given": bool(interview.consent_given),
        "current_index": index,
        "completed_questions": index,
        "total_questions": total,
        "current_question": _question_payload(current) if current else None,
        "answer_processing": processing_summary(interview),
        "answers": [
            {
                "interview_question_id": question.interview_question_id,
                "question_order": question.question_order,
                "question_text": question.question.question_text if question.question else (question.followup_text or ""),
                "transcript": question.analysis.transcript if question.analysis else "",
                "audio_url": f"/interviews/{interview.interview_id}/questions/{question.interview_question_id}/audio",
                "processing_status": (
                    question.processing_job.status if question.processing_job
                    else "NEEDS_REVIEW" if question.needs_review else "PENDING"
                ),
                "evaluation_outcome": question.processing_job.outcome if question.processing_job else None,
            }
            for question in questions
            if question.answer_audio_path
        ],
        "conversation": [
            {
                "interview_question_id": question.interview_question_id,
                "question_id": question.question_id,
                "question_order": question.question_order,
                "question_text": question.question.question_text if question.question else (question.followup_text or ""),
                "asked_at": question.asked_at.isoformat() if question.asked_at else None,
                "transcript": (
                    question.analysis.transcript
                    if question.analysis
                    and question.analysis.transcription_status == "OK"
                    and (question.analysis.transcript or "").strip()
                    else ""
                ),
                "transcription_status": question.analysis.transcription_status if question.analysis else None,
                "transcribed_at": question.analysis.created_at.isoformat()
                if question.analysis and question.analysis.created_at else None,
            }
            for question in questions
            if question.asked_at is not None
        ],
    }


def _question_payload(question):
    if question is None:
        return None
    return {
        "interview_question_id": question.interview_question_id,
        "question_id": question.question_id,
        "question_text": question.question.question_text if question.question else (question.followup_text or ""),
        "question_type": question.question.question_type if question.question else ("Follow-up" if question.is_followup else None),
        "difficulty": question.question.difficulty if question.question else None,
        "question_order": question.question_order,
        "is_followup": bool(question.is_followup),
    }


def _finish_if_exhausted(interview):
    if (interview.current_index or 0) >= len(interview.questions):
        interview.current_index = len(interview.questions)
        interview.status = "PROCESSING"
        if interview.ended_at is None:
            interview.ended_at = datetime.utcnow()
        return True
    return False


def _record_analysis(question, transcription, metrics):
    question.transcript = transcription.get("transcript", "")
    analysis = question.analysis
    if analysis is None:
        analysis = AudioAnalysis(interview_question_id=question.interview_question_id)
        db.session.add(analysis)
        question.analysis = analysis
    analysis.transcript = transcription.get("transcript", "")
    analysis.language_detected = transcription.get("language", "en")
    analysis.transcription_status = transcription.get("status", "ERROR")
    for field in (
        "answer_duration_seconds",
        "speaking_duration_seconds",
        "words_per_minute",
        "pause_count",
        "total_pause_duration_seconds",
        "longest_pause_seconds",
        "filler_word_count",
        "filler_word_rate",
        "repetition_count",
        "speech_ratio",
        "technical_keywords_found",
        "filler_words_found",
        "detected_intent",
        "audio_quality_status",
        "background_noise_level",
        "audio_usable",
        "pitch_mean_hz",
        "pitch_std_hz",
        "rms_mean",
        "rms_std",
        "delivery_score",
        "analysis_json",
    ):
        setattr(analysis, field, metrics.get(field))
    return analysis


def _question_at_current_index(interview):
    questions = sorted(interview.questions, key=lambda row: row.question_order)
    index = interview.current_index or 0
    return questions[index] if 0 <= index < len(questions) else None


def _mark_current_question_asked(interview):
    question = _question_at_current_index(interview)
    if question is not None and question.asked_at is None:
        question.asked_at = datetime.utcnow()


DIFFICULTY_LEVELS = ("easy", "medium", "hard")


def _adaptive_target_difficulty(current_difficulty, content_score):
    if current_difficulty not in DIFFICULTY_LEVELS:
        return None
    try:
        score = float(content_score)
    except (TypeError, ValueError, OverflowError):
        return current_difficulty
    if not math.isfinite(score) or not 0 <= score <= 10:
        return current_difficulty

    current_level = DIFFICULTY_LEVELS.index(current_difficulty)
    strong_threshold = current_app.config.get("ADAPTIVE_STRONG_THRESHOLD", 8.0)
    weak_threshold = current_app.config.get("ADAPTIVE_WEAK_THRESHOLD", 5.0)
    if score >= strong_threshold:
        current_level = min(current_level + 1, len(DIFFICULTY_LEVELS) - 1)
    elif score <= weak_threshold:
        current_level = max(current_level - 1, 0)
    return DIFFICULTY_LEVELS[current_level]


def _select_next_assigned_question(interview, current_question, reference_question=None, content_score=None):
    """Move the best remaining teacher-assigned question into the next sequence slot."""
    rows = sorted(interview.questions, key=lambda row: row.question_order)
    remaining = [
        row for row in rows
        if row.asked_at is None and row.question_id is not None and row.question is not None
    ]
    if not remaining:
        return None

    # A pending answer has no score yet. Keep assigned order until a completed
    # evaluation is available; never guess a score or move an already asked row.
    reference = reference_question or current_question
    current_difficulty = reference.question.difficulty if reference.question else None
    if content_score is None or current_difficulty not in DIFFICULTY_LEVELS:
        return remaining[0]

    target_difficulty = _adaptive_target_difficulty(current_difficulty, content_score)
    if target_difficulty is None:
        return remaining[0]
    else:
        target_level = DIFFICULTY_LEVELS.index(target_difficulty)
        selected = min(
            remaining,
            key=lambda row: (
                abs(DIFFICULTY_LEVELS.index(row.question.difficulty) - target_level)
                if row.question.difficulty in DIFFICULTY_LEVELS else len(DIFFICULTY_LEVELS),
                0 if row.question.difficulty in DIFFICULTY_LEVELS else 1,
                row.question_order,
            ),
        )

    future_rows = [row for row in rows if row.asked_at is None]
    if future_rows and future_rows[0] is selected:
        return selected

    reordered = [selected] + [row for row in future_rows if row is not selected]
    positions = [index for index, row in enumerate(rows) if row.asked_at is None]
    for position, row in zip(positions, reordered):
        row.question_order = position + 1
    return selected


@bp.get("/interviews/<int:interview_id>")
@login_required("student")
def get_interview_session(interview_id):
    interview = _student_interview(interview_id)
    if interview is None:
        return api_error("Interview not found.", "interview_not_found", 404)
    return jsonify(_session_payload(interview))


@bp.post("/interviews/<int:interview_id>/start")
@login_required("student")
def start_interview(interview_id):
    interview = _student_interview(interview_id)
    if interview is None:
        return api_error("Interview not found.", "interview_not_found", 404)
    data = json_object()
    if data is None or data.get("consent") is not True:
        return api_error("Explicit consent is required before the interview can begin.", "consent_required", 400)
    if interview.status == "IN_PROGRESS" and interview.consent_given:
        return jsonify(_session_payload(interview))
    if interview.status != "SCHEDULED":
        return api_error("This interview cannot be started in its current state.", "invalid_interview_state", 409)
    if not interview.questions:
        return api_error("This interview has no questions. Contact your teacher.", "empty_interview", 409)

    interview.consent_given = True
    interview.status = "IN_PROGRESS"
    interview.started_at = datetime.utcnow()
    interview.current_index = 0
    _mark_current_question_asked(interview)
    db.session.commit()
    return jsonify(_session_payload(interview))


@bp.post("/interviews/<int:interview_id>/questions/<int:interview_question_id>/answer")
@login_required("student")
def submit_answer(interview_id, interview_question_id):
    interview = _student_interview(interview_id)
    if interview is None:
        return api_error("Interview not found.", "interview_not_found", 404)
    question = InterviewQuestion.query.filter_by(
        interview_question_id=interview_question_id,
        interview_id=interview.interview_id,
    ).first()
    if question is None or question.question_id is None:
        return api_error("This is not the current interview question.", "question_out_of_order", 409)

    supplied_submission_id = request.form.get("submission_id", "").strip()
    if supplied_submission_id:
        try:
            submission_id = str(uuid.UUID(supplied_submission_id))
        except (ValueError, AttributeError):
            return api_error("submission_id must be a valid UUID.", "invalid_submission_id", 400)
    else:
        # Older clients remain accepted; question-level uniqueness still prevents
        # a second recording from replacing an already accepted answer.
        submission_id = str(uuid.uuid4())

    prior_submission = AnswerProcessingJob.query.filter_by(submission_id=submission_id).first()
    if prior_submission is not None:
        if prior_submission.interview_question_id != question.interview_question_id:
            return api_error("submission_id was already used for another question.", "submission_conflict", 409)
        return jsonify({
            "action": (
                "processing" if interview.status == "PROCESSING"
                else "complete" if interview.status == "COMPLETED"
                else "next"
            ),
            "idempotent_replay": True,
            "answer_job": prior_submission.to_status_dict(),
            "session": _session_payload(interview),
        })

    existing_job = AnswerProcessingJob.query.filter_by(
        interview_question_id=question.interview_question_id
    ).first()
    if existing_job is not None or question.answer_audio_path:
        return api_error("An answer is already saved for this question and cannot be overwritten.", "answer_already_saved", 409)
    if interview.status != "IN_PROGRESS" or not interview.consent_given:
        return api_error("Start the interview and provide consent before submitting an answer.", "interview_not_started", 409)
    current_question = _question_at_current_index(interview)
    if current_question is None or current_question.interview_question_id != question.interview_question_id:
        return api_error("This is not the current interview question.", "question_out_of_order", 409)

    upload = request.files.get("audio")
    if upload is None:
        return api_error("Upload an audio file in the 'audio' field.", "audio_required", 400)
    content_type = (upload.mimetype or "").lower()
    suffix = ALLOWED_AUDIO_TYPES.get(content_type)
    if suffix is None:
        return api_error("Audio must be WebM, Ogg, WAV, MP4, or MP3.", "unsupported_audio_type", 415)
    audio_bytes = upload.read()
    max_size = current_app.config.get("MAX_AUDIO_BYTES", 25 * 1024 * 1024)
    if not audio_bytes:
        return api_error("The uploaded audio file is empty.", "empty_audio", 400)
    if len(audio_bytes) > max_size:
        return api_error(f"Audio exceeds the {max_size // (1024 * 1024)} MB limit.", "audio_too_large", 413)

    storage = get_storage()
    # Keep every physical upload key unique. Concurrent retries with the same
    # client id must never overwrite the first recording before the DB claim wins.
    upload_id = uuid.uuid4().hex
    key = (
        f"interviews/{interview.interview_id}/questions/{question.interview_question_id}"
        f"/answers/{submission_id}-{upload_id}{suffix}"
    )
    try:
        saved_path = storage.put(key, audio_bytes, content_type=content_type)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to store interview answer audio")
        return api_error("Audio could not be stored. Please try again.", "audio_storage_unavailable", 503)

    enqueue_answer(question, submission_id, saved_path)
    reference_question, reference_score = latest_completed_evaluation(interview)
    _select_next_assigned_question(
        interview,
        question,
        reference_question=reference_question,
        content_score=reference_score,
    )
    interview.current_index = (interview.current_index or 0) + 1
    _mark_current_question_asked(interview)
    try:
        interview_ending = _finish_if_exhausted(interview)
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        try:
            storage.delete(saved_path)
        except Exception:
            current_app.logger.exception("Unable to clean up an uncommitted answer upload")
        current_app.logger.warning("Database integrity conflict operation=session.submit_answer error_type=%s", type(exc).__name__)
        prior_submission = AnswerProcessingJob.query.filter_by(submission_id=submission_id).first()
        if prior_submission and prior_submission.interview_question_id == interview_question_id:
            return jsonify({
                "action": "processing" if interview.status == "PROCESSING" else "next",
                "idempotent_replay": True,
                "answer_job": prior_submission.to_status_dict(),
                "session": _session_payload(interview),
            })
        return api_error("An answer is already saved for this question and cannot be overwritten.", "answer_already_saved", 409)
    except Exception:
        db.session.rollback()
        try:
            storage.delete(saved_path)
        except Exception:
            current_app.logger.exception("Unable to clean up an uncommitted answer upload")
        raise
    return jsonify({
        "action": "processing" if interview_ending else "next",
        "answer_job": question.processing_job.to_status_dict(),
        "session": _session_payload(interview),
    })


@bp.post("/interviews/<int:interview_id>/advance")
@login_required("student")
def advance_question(interview_id):
    interview = _student_interview(interview_id)
    if interview is None:
        return api_error("Interview not found.", "interview_not_found", 404)
    if interview.status != "IN_PROGRESS":
        return api_error("Interview is not in progress.", "invalid_interview_state", 409)
    data = json_object()
    if data is None or data.get("intent") not in ("REPEAT", "SKIP", "DONE"):
        return api_error("intent must be REPEAT, SKIP, or DONE.", "invalid_intent", 400)
    if _question_at_current_index(interview) is None:
        return api_error("There are no remaining questions.", "interview_exhausted", 409)
    if data["intent"] == "REPEAT":
        return jsonify({"action": "repeat", "session": _session_payload(interview)})
    if data["intent"] == "DONE":
        interview.current_index = len(interview.questions)
        for pending_question in interview.questions:
            if pending_question.final_ai_score is None and pending_question.teacher_score is None:
                pending_question.needs_review = True
                pending_question.evaluation_json = {"needs_teacher_review": True, "feedback": "Not answered before the interview ended."}
    else:
        question = _question_at_current_index(interview)
        question.needs_review = True
        question.evaluation_json = {"needs_teacher_review": True, "feedback": "Student skipped this question."}
        reference_question, reference_score = latest_completed_evaluation(interview)
        _select_next_assigned_question(
            interview,
            question,
            reference_question=reference_question,
            content_score=reference_score,
        )
        interview.current_index = (interview.current_index or 0) + 1
        _mark_current_question_asked(interview)
    interview_ending = _finish_if_exhausted(interview)
    db.session.commit()
    return jsonify({"action": "processing" if interview_ending else "next", "session": _session_payload(interview)})


@bp.get("/interviews/<int:interview_id>/questions/<int:interview_question_id>/audio")
@login_required()
def get_answer_audio(interview_id, interview_question_id):
    question = InterviewQuestion.query.filter_by(
        interview_question_id=interview_question_id, interview_id=interview_id
    ).first()
    if question is None:
        return api_error("Answer audio not found.", "audio_not_found", 404)
    interview = db.session.get(Interview, interview_id)
    if interview is None:
        return api_error("Answer audio not found.", "audio_not_found", 404)
    allowed = (
        g.user.role == "admin"
        or (g.user.role == "student" and interview.student_id == g.user.user_id)
        or (g.user.role == "teacher" and interview.teacher_id == g.user.user_id)
    )
    if not allowed:
        return api_error("You do not have permission to access this audio.", "forbidden", 403)
    if not question.answer_audio_path:
        return api_error("No answer audio is stored for this question.", "audio_not_found", 404)
    try:
        return get_storage().send(
            question.answer_audio_path,
            download_name=Path(question.answer_audio_path).name,
        )
    except FileNotFoundError:
        return api_error("Stored answer audio is unavailable.", "audio_not_found", 404)
    except Exception:
        current_app.logger.exception("Unable to read stored interview answer audio")
        return api_error("Stored answer audio is temporarily unavailable.", "audio_storage_unavailable", 503)
