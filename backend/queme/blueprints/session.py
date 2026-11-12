from datetime import datetime
from pathlib import Path
from random import sample

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from ..api_errors import api_error, json_object
from ..authz import login_required
from ..extensions import db
from ..models import AudioAnalysis, Interview, InterviewQuestion
from ..services.audio_analysis import analyze_audio
from ..services.llm import generate_followup
from ..services.reports import evaluate_interview_answer, generate_interview_report
from ..services.storage import get_storage
from ..services.transcription import transcribe

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
INTENT_COMMANDS = {"REPEAT", "SKIP", "DONE"}


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
        "answers": [
            {
                "interview_question_id": question.interview_question_id,
                "question_order": question.question_order,
                "question_text": question.question.question_text if question.question else (question.followup_text or ""),
                "transcript": question.analysis.transcript if question.analysis else "",
                "audio_url": f"/interviews/{interview.interview_id}/questions/{question.interview_question_id}/audio",
            }
            for question in questions
            if question.answer_audio_path
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
        interview.status = "COMPLETED"
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


def _insert_followup(interview, question, text):
    text = text.strip()
    if not text or len(text) > 1000:
        return None
    for later in sorted(
        (row for row in interview.questions if row.question_order > question.question_order),
        key=lambda row: row.question_order,
        reverse=True,
    ):
        later.question_order += 1
    followup = InterviewQuestion(
        interview=interview,
        question_order=question.question_order + 1,
        rubric_id=question.rubric_id,
        followup_text=text,
        is_followup=True,
    )
    db.session.add(followup)
    return followup


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
    if interview.status != "IN_PROGRESS" or not interview.consent_given:
        return api_error("Start the interview and provide consent before submitting an answer.", "interview_not_started", 409)
    question = _question_at_current_index(interview)
    if question is None or question.interview_question_id != interview_question_id:
        return api_error("This is not the current interview question.", "question_out_of_order", 409)
    if question.answer_audio_path and question.analysis and question.analysis.audio_usable:
        return api_error("This answer is already saved.", "answer_already_saved", 409)

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

    transcription = transcribe(audio_bytes, suffix=suffix)
    transcript = transcription.get("transcript", "")
    metrics = analyze_audio(
        audio_bytes,
        transcript,
        transcription.get("words", []),
        question.question.expected_key_points if question.question else "",
    )
    intent = metrics.get("detected_intent", "ANSWER")
    if intent in INTENT_COMMANDS and question.answer_audio_path:
        try:
            get_storage().delete(question.answer_audio_path)
            question.answer_audio_path = None
            if question.analysis is not None:
                db.session.delete(question.analysis)
                question.analysis = None
        except Exception:
            current_app.logger.exception("Unable to replace a previous poor quality answer")
            return api_error("The previous recording could not be cleared. Please contact your teacher.", "audio_storage_unavailable", 503)
    if intent == "REPEAT":
        db.session.commit()
        return jsonify({
            "action": "repeat",
            "message": "Repeating the current question.",
            "transcript": transcript,
            "session": _session_payload(interview),
        })

    if intent == "DONE":
        question.needs_review = True
        question.evaluation_json = {"needs_teacher_review": True, "feedback": "Student ended the interview before this question was answered."}
        for pending_question in interview.questions:
            if pending_question.question_order > question.question_order and pending_question.final_ai_score is None:
                pending_question.needs_review = True
                pending_question.evaluation_json = {"needs_teacher_review": True, "feedback": "Not answered before the interview ended."}
        interview.current_index = len(interview.questions)
        completed = _finish_if_exhausted(interview)
        if completed:
            generate_interview_report(interview)
        db.session.commit()
        return jsonify({
            "action": "complete" if completed else "next",
            "intent": intent,
            "message": "Interview complete." if completed else "Moving to the next question.",
            "session": _session_payload(interview),
        })

    if intent == "SKIP":
        question.needs_review = True
        question.evaluation_json = {"needs_teacher_review": True, "feedback": "Student skipped this question."}
        interview.current_index = (interview.current_index or 0) + 1
        _mark_current_question_asked(interview)
        completed = _finish_if_exhausted(interview)
        if completed:
            generate_interview_report(interview)
        db.session.commit()
        return jsonify({
            "action": "complete" if completed else "next",
            "intent": intent,
            "message": "Interview complete." if completed else "Moving to the next question.",
            "session": _session_payload(interview),
        })

    key = f"interviews/{interview.interview_id}/questions/{question.interview_question_id}/answer{suffix}"
    try:
        question.answer_audio_path = get_storage().put(key, audio_bytes, content_type=content_type)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to store interview answer audio")
        return api_error("Audio could not be stored. Please try again.", "audio_storage_unavailable", 503)

    quality = metrics.get("audio_quality_status") or "UNKNOWN"
    if quality == "POOR":
        _record_analysis(question, transcription, metrics)
        db.session.commit()
        return jsonify({
            "action": "retry",
            "message": "The recording was too quiet or too short. Please try again.",
            "transcript": transcript,
            "session": _session_payload(interview),
        })

    _record_analysis(question, transcription, metrics)
    evaluate_interview_answer(question)
    if (
        not question.is_followup
        and transcription.get("status") == "OK"
        and metrics.get("audio_usable") is True
    ):
        followup_text = generate_followup(
            question.question.question_text if question.question else (question.followup_text or ""),
            transcript,
            question.question.question_type if question.question else "",
        )
        if followup_text:
            _insert_followup(interview, question, followup_text)
    interview.current_index = (interview.current_index or 0) + 1
    _mark_current_question_asked(interview)
    completed = _finish_if_exhausted(interview)
    if completed:
        generate_interview_report(interview)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        current_app.logger.warning("Database integrity conflict operation=session.submit_answer error_type=%s", type(exc).__name__)
        return api_error("The answer could not be saved. Please retry.", "answer_save_conflict", 409)
    return jsonify({
        "action": "complete" if completed else "next",
        "transcript": transcript,
        "transcription_status": transcription.get("status"),
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
        interview.current_index = (interview.current_index or 0) + 1
        _mark_current_question_asked(interview)
    completed = _finish_if_exhausted(interview)
    if completed:
        generate_interview_report(interview)
    db.session.commit()
    return jsonify({"action": "complete" if completed else "next", "session": _session_payload(interview)})


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
