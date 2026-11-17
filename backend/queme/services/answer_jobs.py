"""Durable, single-worker processing for recorded interview answers."""
from datetime import datetime, timedelta
import fcntl
import json
import logging
import os
from pathlib import Path
import time

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_

from ..extensions import db
from ..models import AnswerProcessingJob, Interview, InterviewQuestion
from .audio_analysis import analyze_audio
from .reports import evaluate_interview_answer, generate_interview_report
from .storage import get_storage
from .transcription import transcribe

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
RETRY_BASE_SECONDS = 5
ACTIVE_STATUSES = ("QUEUED", "PROCESSING", "RETRY_WAIT")
TERMINAL_STATUSES = ("COMPLETED", "NEEDS_REVIEW")
WORKER_HEARTBEAT_FILE = "answer-processing-worker.json"
WORKER_HEARTBEAT_STALE_SECONDS = 30
MAX_DATABASE_RETRY_SECONDS = 30


def _write_worker_heartbeat(
    state, *, consecutive_failures=0, job_id=None, last_job_id=None,
    last_processed_at=None, poll_seconds=1
):
    path = Path(current_app.instance_path) / WORKER_HEARTBEAT_FILE
    payload = {
        "pid": os.getpid(),
        "heartbeat_at": time.time(),
        "state": state,
        "consecutive_failures": consecutive_failures,
        "job_id": job_id,
        "last_job_id": last_job_id,
        "last_processed_at": last_processed_at,
        "poll_seconds": poll_seconds,
    }
    temporary_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        temporary_path.write_text(json.dumps(payload), encoding="utf-8")
        temporary_path.replace(path)
    except OSError:
        logger.warning("Answer worker heartbeat could not be written", exc_info=True)
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def worker_health():
    """Report worker liveness from its lock and fresh heartbeat, without a DB query."""
    lock_path = Path(current_app.instance_path) / "answer-processing-worker.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            return {"status": "not_running", "running": False}

    heartbeat_path = lock_path.with_name(WORKER_HEARTBEAT_FILE)
    try:
        payload = json.loads(heartbeat_path.read_text(encoding="utf-8"))
        heartbeat_age = max(0, time.time() - float(payload["heartbeat_at"]))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return {"status": "unhealthy", "running": True, "reason": "heartbeat_unavailable"}

    failures = int(payload.get("consecutive_failures", 0))
    state = payload.get("state")
    stale_after = max(
        WORKER_HEARTBEAT_STALE_SECONDS,
        float(payload.get("poll_seconds", 1)) * 3,
        max(
            float(current_app.config.get("OLLAMA_TIMEOUT", 300)) + 30,
            float(current_app.config.get("DUAL_EVALUATION_BUDGET_SECONDS", 750)) + 30
            if current_app.config.get("EVALUATION_MODE", "dual_sequential") == "dual_sequential"
            else 0,
        )
        if state == "processing" else WORKER_HEARTBEAT_STALE_SECONDS,
    )
    if heartbeat_age > stale_after:
        status = "unhealthy"
        reason = "stale_heartbeat"
    elif failures >= 3:
        status = "failing"
        reason = "repeated_database_failures"
    elif state == "starting":
        status = "unhealthy"
        reason = "starting"
    elif state == "retrying":
        status = "unhealthy"
        reason = "database_retry"
    elif state == "idle":
        status = "inactive"
        reason = None
    else:
        status = "healthy"
        reason = None
    return {
        "status": status,
        "running": True,
        "reason": reason,
        "heartbeat_age_seconds": round(heartbeat_age, 1),
        "consecutive_failures": failures,
        "last_job_id": payload.get("last_job_id"),
        "last_processed_at": payload.get("last_processed_at"),
    }


def _restore_interrupted_job(job):
    question = job.question
    needs_review = question.needs_review or bool(
        isinstance(question.evaluation_json, dict)
        and question.evaluation_json.get("needs_teacher_review")
    )
    if question.content_score is not None and not needs_review:
        job.status = "COMPLETED"
        job.outcome = "EVALUATED"
        job.finished_at = job.finished_at or datetime.utcnow()
    elif needs_review:
        job.status = "NEEDS_REVIEW"
        job.outcome = "TEACHER_REVIEW"
        job.finished_at = job.finished_at or datetime.utcnow()
    else:
        job.status = "QUEUED"
    job.locked_at = None


def _recover_claimed_job(job_id):
    """Restore only this worker's interrupted claim after a database outage."""
    job = db.session.get(AnswerProcessingJob, job_id)
    if job is not None and job.status == "PROCESSING":
        _restore_interrupted_job(job)
        db.session.commit()


def enqueue_answer(question, submission_id, audio_path):
    job = AnswerProcessingJob(
        question=question,
        submission_id=submission_id,
        audio_path=audio_path,
        status="QUEUED",
        stage="TRANSCRIPTION",
    )
    question.answer_audio_path = audio_path
    question.needs_review = False
    db.session.add(job)
    return job


def processing_summary(interview):
    summary = {
        "total": 0,
        "successfully_evaluated": 0,
        "pending": 0,
        "retryable_failures": 0,
        "teacher_review": 0,
    }
    for question in interview.questions:
        job = question.processing_job
        if question.answer_audio_path:
            summary["total"] += 1
            if job is None or job.status in ("QUEUED", "PROCESSING"):
                summary["pending"] += 1
            elif job.status == "RETRY_WAIT":
                summary["retryable_failures"] += 1
            elif job.status == "NEEDS_REVIEW" or job.outcome == "TEACHER_REVIEW":
                summary["teacher_review"] += 1
            elif job.status == "COMPLETED" and job.outcome == "EVALUATED":
                summary["successfully_evaluated"] += 1
            else:
                summary["teacher_review"] += 1
        elif question.needs_review:
            summary["teacher_review"] += 1
    summary["finished"] = summary["pending"] == 0 and summary["retryable_failures"] == 0
    return summary


def latest_completed_evaluation(interview, before_order=None):
    query = (
        AnswerProcessingJob.query.join(InterviewQuestion)
        .filter(
            InterviewQuestion.interview_id == interview.interview_id,
            AnswerProcessingJob.status == "COMPLETED",
            AnswerProcessingJob.outcome == "EVALUATED",
        )
    )
    if before_order is not None:
        query = query.filter(InterviewQuestion.question_order < before_order)
    job = query.order_by(AnswerProcessingJob.finished_at.desc(), AnswerProcessingJob.job_id.desc()).first()
    if job is None or job.question.content_score is None:
        return None, None
    return job.question, float(job.question.content_score)


def _mark_teacher_review(job, reason_code, reason_message):
    question = job.question
    question.needs_review = True
    evaluation = question.evaluation_json if isinstance(question.evaluation_json, dict) else {}
    evaluation.update({
        "needs_teacher_review": True,
        "error": reason_message,
    })
    if question.content_score is None:
        evaluation["evaluation_status"] = "UNAVAILABLE"
    question.evaluation_json = evaluation
    job.status = "NEEDS_REVIEW"
    job.outcome = "TEACHER_REVIEW"
    job.finished_at = datetime.utcnow()
    job.locked_at = None
    job.last_error_code = reason_code
    job.last_error_message = reason_message[:300]


def _retry_or_review(job, error_code, safe_message, *, retryable=True):
    job.locked_at = None
    job.last_error_code = error_code
    job.last_error_message = safe_message[:300]
    if not retryable or job.attempt_count >= MAX_ATTEMPTS:
        _mark_teacher_review(job, error_code, safe_message)
        if job.stage == "EVALUATION":
            logger.warning(
                "Answer evaluation stopped job_id=%s attempt=%d max_attempts=%d reason=%s retryable=%s outcome=teacher_review",
                job.job_id, job.attempt_count, MAX_ATTEMPTS, error_code, retryable,
            )
        return
    delay = RETRY_BASE_SECONDS * (2 ** max(job.attempt_count - 1, 0))
    job.status = "RETRY_WAIT"
    job.available_at = datetime.utcnow() + timedelta(seconds=delay)
    if job.stage == "EVALUATION":
        logger.warning(
            "Answer evaluation retry scheduled job_id=%s attempt=%d max_attempts=%d reason=%s retry_delay_s=%d",
            job.job_id, job.attempt_count, MAX_ATTEMPTS, error_code, delay,
        )


def _claim_next_job():
    now = datetime.utcnow()
    job = (
        AnswerProcessingJob.query.filter(
            AnswerProcessingJob.status.in_(("QUEUED", "RETRY_WAIT")),
            AnswerProcessingJob.available_at <= now,
        )
        .order_by(AnswerProcessingJob.created_at, AnswerProcessingJob.job_id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        return None
    job.status = "PROCESSING"
    job.locked_at = now
    job.attempt_count += 1
    db.session.commit()
    return job.job_id


def _finish_if_ready(interview_id):
    interview = (
        db.session.query(Interview)
        .filter_by(interview_id=interview_id)
        .with_for_update()
        .first()
    )
    if interview is None or interview.status != "PROCESSING":
        return False
    active = (
        AnswerProcessingJob.query.join(InterviewQuestion)
        .filter(
            InterviewQuestion.interview_id == interview_id,
            AnswerProcessingJob.status.in_(ACTIVE_STATUSES),
        )
        .count()
    )
    unqueued_answers = InterviewQuestion.query.filter_by(interview_id=interview_id).filter(
        InterviewQuestion.answer_audio_path.isnot(None),
        ~InterviewQuestion.processing_job.has(),
    ).count()
    if active or unqueued_answers:
        return False
    generate_interview_report(interview)
    interview.status = "COMPLETED"
    db.session.commit()
    logger.info("Interview processing finalized interview_id=%s", interview_id)
    return True


def _finish_ready_interviews():
    ids = [
        row.interview_id
        for row in Interview.query.filter_by(status="PROCESSING").order_by(Interview.interview_id).all()
    ]
    for interview_id in ids:
        try:
            _finish_if_ready(interview_id)
        except Exception as exc:
            db.session.rollback()
            logger.warning("Interview finalization deferred interview_id=%s error_type=%s", interview_id, type(exc).__name__)


def _safe_finish_interview(interview_id):
    db.session.remove()
    try:
        _finish_if_ready(interview_id)
    except Exception as exc:
        db.session.rollback()
        logger.warning("Interview finalization deferred interview_id=%s error_type=%s", interview_id, type(exc).__name__)


def process_job(job_id):
    """Run or resume one claimed job, committing each successful processing stage."""
    job = db.session.get(AnswerProcessingJob, job_id)
    if job is None or job.status != "PROCESSING":
        return
    interview_id = job.question.interview_id
    try:
        storage = get_storage()
        audio_bytes = storage.get(job.audio_path)

        if job.stage == "TRANSCRIPTION":
            suffix = Path(job.audio_path).suffix or ".webm"
            transcription = transcribe(audio_bytes, suffix=suffix)
            status = transcription.get("status")
            if status in ("ERROR", "UNAVAILABLE"):
                _retry_or_review(job, "transcription_unavailable", "Transcription could not complete after retry attempts.")
                db.session.commit()
                _safe_finish_interview(interview_id)
                return

            transcript = transcription.get("transcript") or ""
            metrics = analyze_audio(
                audio_bytes,
                transcript,
                transcription.get("words", []),
                job.question.question.expected_key_points if job.question.question else "",
            )
            from ..blueprints.session import _record_analysis

            _record_analysis(job.question, transcription, metrics)
            if status != "OK" or not transcript.strip():
                _mark_teacher_review(job, "transcript_unavailable", "The saved recording has no usable transcript.")
                db.session.commit()
                _safe_finish_interview(interview_id)
                return
            if metrics.get("audio_quality_status") == "POOR" or metrics.get("audio_usable") is False:
                _mark_teacher_review(job, "audio_quality_insufficient", "The saved recording did not meet audio quality checks.")
                db.session.commit()
                _safe_finish_interview(interview_id)
                return

            job.stage = "EVALUATION"
            job.status = "PROCESSING"
            job.locked_at = datetime.utcnow()
            db.session.commit()

        evaluation_started = time.monotonic()
        evaluation_budget = int(current_app.config.get(
            "DUAL_EVALUATION_BUDGET_SECONDS", 750
        ) if current_app.config.get("EVALUATION_MODE", "dual_sequential") == "dual_sequential"
            else current_app.config.get("OLLAMA_EVALUATION_BUDGET_SECONDS", 600))
        evaluation = evaluate_interview_answer(
            job.question,
            correlation_id=f"answer_job:{job.job_id}",
        )
        evaluation_elapsed = time.monotonic() - evaluation_started
        score = job.question.content_score
        evaluation_error = str(evaluation.get("error") or "")
        dual_state = evaluation.get("dual_model") if isinstance(evaluation.get("dual_model"), dict) else {}
        if dual_state.get("retryable") or evaluation.get("retryable"):
            budget_exceeded = evaluation_elapsed >= evaluation_budget
            _retry_or_review(
                job,
                "evaluation_budget_exceeded" if budget_exceeded else "provider_transient_failure",
                "The sequential evaluation exceeded its processing budget and requires teacher review."
                if budget_exceeded else "A temporary AI evaluation service failure requires a bounded retry.",
                retryable=not budget_exceeded,
            )
        elif evaluation.get("error_category") in ("invalid_response", "invalid_json", "schema_validation") or evaluation_error.startswith("Local Ollama returned invalid structured content"):
            _retry_or_review(
                job,
                "invalid_evaluation_output",
                "Automatic evaluation returned incomplete or invalid results after its repair attempt.",
                retryable=False,
            )
        elif evaluation_error.startswith("Local Ollama"):
            budget_exceeded = evaluation_elapsed >= evaluation_budget
            _retry_or_review(
                job,
                "evaluation_budget_exceeded" if budget_exceeded else "ollama_unavailable",
                "Automatic evaluation exceeded its processing budget and requires teacher review."
                if budget_exceeded else "Automatic evaluation could not reach the local AI service.",
                retryable=not budget_exceeded,
            )
        elif score is not None and not job.question.needs_review:
            job.status = "COMPLETED"
            job.outcome = "EVALUATED"
            job.finished_at = datetime.utcnow()
            job.locked_at = None
            job.last_error_code = None
            job.last_error_message = None
        else:
            reason_code = "evidence_unavailable" if evaluation.get("review_reason") == "evidence_unavailable" else "evaluation_unavailable"
            safe_message = (
                "Evaluation evidence could not be verified against the saved transcript."
                if reason_code == "evidence_unavailable"
                else "Automatic evaluation did not produce a complete score."
            )
            _mark_teacher_review(job, reason_code, safe_message)
        db.session.commit()
        logger.info(
            "Answer evaluation job updated job_id=%s status=%s outcome=%s duration_ms=%d",
            job.job_id, job.status, job.outcome or "-",
            int((time.monotonic() - evaluation_started) * 1000),
        )
    except Exception as exc:
        db.session.rollback()
        job = db.session.get(AnswerProcessingJob, job_id)
        if job is not None:
            _retry_or_review(job, "processing_error", "Answer processing failed and will be retried.")
            interview_id = job.question.interview_id
            db.session.commit()
        logger.warning("Answer processing attempt failed job_id=%s error_type=%s", job_id, type(exc).__name__)

    db.session.remove()
    if interview_id is not None:
        _safe_finish_interview(interview_id)


def recover_interrupted_jobs():
    """Recover jobs interrupted by a worker restart and enqueue legacy saved answers."""
    for job in AnswerProcessingJob.query.filter_by(status="PROCESSING").all():
        _restore_interrupted_job(job)

    existing_question_ids = {
        job.interview_question_id for job in AnswerProcessingJob.query.with_entities(
            AnswerProcessingJob.interview_question_id
        ).all()
    }
    legacy_answers = (
        InterviewQuestion.query.join(Interview)
        .filter(
            InterviewQuestion.answer_audio_path.isnot(None),
            Interview.status.in_(("IN_PROGRESS", "PROCESSING")),
        )
        .all()
    )
    for question in legacy_answers:
        if question.interview_question_id in existing_question_ids:
            continue
        analysis = question.analysis
        evaluated = question.content_score is not None
        needs_review = question.needs_review or bool(
            isinstance(question.evaluation_json, dict)
            and question.evaluation_json.get("needs_teacher_review")
        )
        if evaluated and not needs_review:
            status, outcome, stage = "COMPLETED", "EVALUATED", "EVALUATION"
        elif needs_review:
            status, outcome, stage = "NEEDS_REVIEW", "TEACHER_REVIEW", "EVALUATION"
        elif analysis and analysis.transcription_status == "OK" and (analysis.transcript or "").strip():
            status, outcome, stage = "QUEUED", None, "EVALUATION"
        else:
            status, outcome, stage = "QUEUED", None, "TRANSCRIPTION"
        db.session.add(AnswerProcessingJob(
            question=question,
            submission_id=f"legacy-{question.interview_question_id}",
            audio_path=question.answer_audio_path,
            status=status,
            outcome=outcome,
            stage=stage,
            attempt_count=0,
            finished_at=datetime.utcnow() if status in TERMINAL_STATUSES else None,
        ))
    db.session.commit()
    _finish_ready_interviews()


def run_worker(*, once=False, poll_seconds=1):
    """Run one local worker. The OS lock prevents duplicate worker processes."""
    lock_dir = Path(current_app.instance_path)
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = (lock_dir / "answer-processing-worker.lock").open("a+")
    try:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("An answer-processing worker is already running on this host.") from exc
        recovered = False
        consecutive_database_failures = 0
        interrupted_job_id = None
        last_job_id = None
        last_processed_at = None
        _write_worker_heartbeat("starting", poll_seconds=poll_seconds)
        while True:
            job_id = None
            try:
                if not recovered:
                    recover_interrupted_jobs()
                    recovered = True
                if interrupted_job_id is not None:
                    _recover_claimed_job(interrupted_job_id)
                    interrupted_job_id = None
                _finish_ready_interviews()
                job_id = _claim_next_job()
                if job_id is None:
                    consecutive_database_failures = 0
                    _write_worker_heartbeat(
                        "idle", last_job_id=last_job_id,
                        last_processed_at=last_processed_at,
                        poll_seconds=poll_seconds,
                    )
                    if once:
                        return
                    time.sleep(max(0.1, poll_seconds))
                    continue

                _write_worker_heartbeat(
                    "processing", job_id=job_id, poll_seconds=poll_seconds
                )
                process_job(job_id)
                consecutive_database_failures = 0
                last_job_id = job_id
                last_processed_at = time.time()
                _write_worker_heartbeat(
                    "idle", last_job_id=last_job_id,
                    last_processed_at=last_processed_at,
                    poll_seconds=poll_seconds,
                )
                if once:
                    return
            except SQLAlchemyError:
                db.session.rollback()
                db.session.remove()
                consecutive_database_failures += 1
                if job_id is not None:
                    interrupted_job_id = job_id
                retry_delay = min(
                    MAX_DATABASE_RETRY_SECONDS,
                    max(1, 2 ** min(consecutive_database_failures - 1, 5)),
                )
                _write_worker_heartbeat(
                    "retrying",
                    consecutive_failures=consecutive_database_failures,
                    job_id=interrupted_job_id,
                    last_job_id=last_job_id,
                    last_processed_at=last_processed_at,
                    poll_seconds=retry_delay,
                )
                logger.exception(
                    "Answer worker database operation failed; retrying in %s seconds",
                    retry_delay,
                )
                time.sleep(retry_delay)
    finally:
        lock_file.close()

