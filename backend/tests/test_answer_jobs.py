import fcntl
import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.exc import OperationalError
from unittest.mock import patch

from queme import create_app
from queme.extensions import db
from queme.models import (
    AnswerProcessingJob,
    AudioAnalysis,
    Interview,
    InterviewQuestion,
    InterviewTemplate,
    QuestionBank,
    User,
)
from queme.services.answer_jobs import (
    WORKER_HEARTBEAT_FILE,
    _retry_or_review,
    _write_worker_heartbeat,
    processing_summary,
    run_worker,
    worker_health,
)


class AnswerJobTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "JWT_EXP_HOURS": 24,
            "SECRET_KEY": "test-secret-key-that-is-long-enough-for-tests",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "STORAGE_BACKEND": "local",
            "STORAGE_LOCAL_DIR": Path(self.temp_dir.name),
            "FRONTEND_ORIGIN": "http://localhost:5173",
            "OLLAMA_BASE_URL": "http://localhost:11434",
            "EVALUATION_MODE": "single_provider",
            "EVALUATION_PROVIDER": "ollama",
        })
        self.app.instance_path = self.temp_dir.name
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        teacher = User(full_name="Teacher", email="teacher@example.test", password_hash="x", role="teacher", account_status="ACTIVE")
        student = User(full_name="Student", email="student@example.test", password_hash="x", role="student", account_status="ACTIVE")
        db.session.add_all([teacher, student])
        db.session.flush()
        template = InterviewTemplate(title="Practice", created_by=teacher.user_id)
        question = QuestionBank(
            created_by=teacher.user_id,
            question_text="Explain a primary key.",
            question_type="technical",
            difficulty="medium",
        )
        db.session.add_all([template, question])
        db.session.flush()
        self.interview = Interview(
            student_id=student.user_id,
            teacher_id=teacher.user_id,
            template_id=template.template_id,
            status="PROCESSING",
            consent_given=True,
            current_index=1,
            ended_at=datetime.utcnow(),
        )
        db.session.add(self.interview)
        db.session.flush()
        self.question = InterviewQuestion(
            interview_id=self.interview.interview_id,
            question_id=question.question_id,
            question_order=1,
            asked_at=datetime.utcnow(),
            answer_audio_path="interviews/1/questions/1/answers/submission.webm",
        )
        db.session.add(self.question)
        db.session.flush()
        self.job = AnswerProcessingJob(
            question=self.question,
            submission_id="c341feaf-a749-42b7-87d2-265a559c1534",
            audio_path=self.question.answer_audio_path,
            status="QUEUED",
            stage="TRANSCRIPTION",
        )
        db.session.add(self.job)
        db.session.commit()
        self.interview_id = self.interview.interview_id
        self.question_id = self.question.interview_question_id
        self.job_id = self.job.job_id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.temp_dir.cleanup()

    def test_transient_failures_retry_then_finish_for_teacher_review_without_zero_score(self):
        storage = type("StorageStub", (), {"get": lambda _self, _key: b"saved audio"})()
        with (
            patch("queme.services.answer_jobs.get_storage", return_value=storage),
            patch("queme.services.answer_jobs.transcribe", return_value={"transcript": "", "words": [], "status": "UNAVAILABLE"}),
        ):
            run_worker(once=True)
            job = db.session.get(AnswerProcessingJob, self.job_id)
            self.assertEqual(job.status, "RETRY_WAIT")
            job.available_at = datetime.utcnow() - timedelta(seconds=1)
            db.session.commit()
            run_worker(once=True)
            job = db.session.get(AnswerProcessingJob, self.job_id)
            self.assertEqual(job.status, "RETRY_WAIT")
            job.available_at = datetime.utcnow() - timedelta(seconds=1)
            db.session.commit()
            run_worker(once=True)

        job = db.session.get(AnswerProcessingJob, self.job_id)
        question = db.session.get(InterviewQuestion, self.question_id)
        interview = db.session.get(Interview, self.interview_id)
        self.assertEqual(job.status, "NEEDS_REVIEW")
        self.assertEqual(job.outcome, "TEACHER_REVIEW")
        self.assertIsNone(question.content_score)
        self.assertIsNone(question.final_ai_score)
        self.assertEqual(interview.status, "COMPLETED")
        self.assertIsNone(interview.report.final_score)
        summary = processing_summary(interview)
        self.assertEqual(summary["successfully_evaluated"], 0)
        self.assertEqual(summary["pending"], 0)
        self.assertEqual(summary["retryable_failures"], 0)
        self.assertEqual(summary["teacher_review"], 1)

    def test_restart_resumes_at_evaluation_stage_without_retranscribing(self):
        job = db.session.get(AnswerProcessingJob, self.job_id)
        question = db.session.get(InterviewQuestion, self.question_id)
        job.status = "PROCESSING"
        job.stage = "EVALUATION"
        job.attempt_count = 1
        question.transcript = "A primary key identifies a row."
        question.analysis = AudioAnalysis(
            interview_question_id=question.interview_question_id,
            transcript=question.transcript,
            transcription_status="OK",
            audio_usable=True,
            audio_quality_status="OK",
            delivery_score=7.0,
        )
        db.session.commit()
        storage = type("StorageStub", (), {"get": lambda _self, _key: b"saved audio"})()

        def evaluate(question, *, correlation_id=None):
            self.assertEqual(correlation_id, f"answer_job:{self.job_id}")
            question.content_score = 8.0
            question.final_ai_score = 7.7
            question.needs_review = False
            question.evaluation_json = {"needs_teacher_review": False}
            return question.evaluation_json

        with (
            patch("queme.services.answer_jobs.get_storage", return_value=storage),
            patch("queme.services.answer_jobs.transcribe") as transcribe,
            patch("queme.services.answer_jobs.evaluate_interview_answer", side_effect=evaluate),
        ):
            with self.assertLogs("queme.services.answer_jobs", level="INFO") as captured:
                run_worker(once=True)

        transcribe.assert_not_called()
        job = db.session.get(AnswerProcessingJob, self.job_id)
        interview = db.session.get(Interview, self.interview_id)
        self.assertEqual(job.status, "COMPLETED")
        self.assertEqual(job.outcome, "EVALUATED")
        self.assertEqual(interview.status, "COMPLETED")
        self.assertEqual(float(interview.report.final_score), 7.7)
        self.assertIn(
            f"Answer evaluation job updated job_id={self.job_id} status=COMPLETED outcome=EVALUATED",
            "\n".join(captured.output),
        )

    def test_restart_resumes_interrupted_transcription_stage(self):
        job = db.session.get(AnswerProcessingJob, self.job_id)
        job.status = "PROCESSING"
        job.stage = "TRANSCRIPTION"
        job.attempt_count = 1
        db.session.commit()
        storage = type("StorageStub", (), {"get": lambda _self, _key: b"saved audio"})()

        def evaluate(question, *, correlation_id=None):
            question.content_score = 8.0
            question.delivery_score = 7.0
            question.final_ai_score = 7.7
            question.needs_review = False
            question.evaluation_json = {"needs_teacher_review": False}
            return question.evaluation_json

        with (
            patch("queme.services.answer_jobs.get_storage", return_value=storage),
            patch("queme.services.answer_jobs.transcribe", return_value={
                "transcript": "A primary key identifies a row.", "words": [], "status": "OK",
            }) as transcribe,
            patch("queme.services.answer_jobs.analyze_audio", return_value={
                "audio_quality_status": "OK", "audio_usable": True,
            }),
            patch("queme.services.answer_jobs.evaluate_interview_answer", side_effect=evaluate) as evaluate_answer,
        ):
            run_worker(once=True)

        transcribe.assert_called_once()
        evaluate_answer.assert_called_once()
        self.assertEqual(db.session.get(AnswerProcessingJob, self.job_id).status, "COMPLETED")
        self.assertEqual(AudioAnalysis.query.filter_by(interview_question_id=self.question_id).count(), 1)

    def test_restart_preserves_already_persisted_evaluation(self):
        job = db.session.get(AnswerProcessingJob, self.job_id)
        question = db.session.get(InterviewQuestion, self.question_id)
        job.status = "PROCESSING"
        job.stage = "EVALUATION"
        question.content_score = 8.0
        question.needs_review = False
        question.evaluation_json = {"needs_teacher_review": False}
        db.session.commit()

        with patch("queme.services.answer_jobs.evaluate_interview_answer") as evaluate:
            run_worker(once=True)

        evaluate.assert_not_called()
        job = db.session.get(AnswerProcessingJob, self.job_id)
        self.assertEqual(job.status, "COMPLETED")
        self.assertEqual(job.outcome, "EVALUATED")

    def test_worker_retries_a_temporary_database_error(self):
        unavailable = OperationalError("SELECT", {}, Exception("database unavailable"))
        with patch(
            "queme.services.answer_jobs._claim_next_job",
            side_effect=[unavailable, self.job_id],
        ) as claim, patch("queme.services.answer_jobs.time.sleep") as sleep, patch(
            "queme.services.answer_jobs.process_job"
        ) as process_job:
            with self.assertLogs("queme.services.answer_jobs", level="ERROR"):
                run_worker(once=True)

        self.assertEqual(claim.call_count, 2)
        sleep.assert_called_once_with(1)
        process_job.assert_called_once_with(self.job_id)

    def test_existing_worker_lock_prevents_a_duplicate_worker(self):
        lock_path = Path(self.app.instance_path) / "answer-processing-worker.lock"
        with lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, "already running"):
                run_worker(once=True)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def test_worker_health_distinguishes_stopped_idle_failing_and_stale(self):
        self.assertEqual(worker_health()["status"], "not_running")
        lock_path = Path(self.app.instance_path) / "answer-processing-worker.lock"
        heartbeat_path = Path(self.app.instance_path) / WORKER_HEARTBEAT_FILE
        with lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _write_worker_heartbeat("idle")
            self.assertEqual(worker_health()["status"], "inactive")
            _write_worker_heartbeat("processing")
            self.assertEqual(worker_health()["status"], "healthy")
            _write_worker_heartbeat("retrying", consecutive_failures=3)
            self.assertEqual(worker_health()["status"], "failing")
            payload = json.loads(heartbeat_path.read_text(encoding="utf-8"))
            payload["heartbeat_at"] = time.time() - 60
            heartbeat_path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(worker_health()["reason"], "stale_heartbeat")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        self.assertEqual(worker_health()["status"], "not_running")

    def test_health_endpoint_reports_database_and_worker_state(self):
        response = self.app.test_client().get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["database"], "ok")
        self.assertEqual(response.json["worker"]["status"], "not_running")

    def test_evaluation_retry_logs_safe_reason_and_schedule(self):
        job = db.session.get(AnswerProcessingJob, self.job_id)
        job.stage = "EVALUATION"
        job.attempt_count = 1
        with self.assertLogs("queme.services.answer_jobs", level="WARNING") as captured:
            _retry_or_review(job, "ollama_unavailable", "Safe internal message.")
        self.assertEqual(job.status, "RETRY_WAIT")
        self.assertIn(
            f"Answer evaluation retry scheduled job_id={self.job_id} attempt=1 max_attempts=3 "
            "reason=ollama_unavailable retry_delay_s=5",
            "\n".join(captured.output),
        )

    def _prepare_evaluation_job(self):
        job = db.session.get(AnswerProcessingJob, self.job_id)
        job.stage = "EVALUATION"
        question = db.session.get(InterviewQuestion, self.question_id)
        question.transcript = "A primary key identifies a row."
        question.analysis = AudioAnalysis(
            interview_question_id=question.interview_question_id,
            transcript=question.transcript,
            transcription_status="OK",
            audio_usable=True,
            audio_quality_status="OK",
            delivery_score=7.0,
        )
        db.session.commit()

    def test_invalid_evaluation_is_terminal_teacher_review_and_finalizes_report(self):
        self._prepare_evaluation_job()
        storage = type("StorageStub", (), {"get": lambda _self, _key: b"saved audio"})()
        invalid = {
            "criteria_scores": {}, "content_score": None, "needs_teacher_review": True,
            "error": "Local Ollama returned invalid structured content after its repair attempt.",
        }
        with (
            patch("queme.services.answer_jobs.get_storage", return_value=storage),
            patch("queme.services.answer_jobs.evaluate_interview_answer", return_value=invalid) as evaluate,
        ):
            run_worker(once=True)

        evaluate.assert_called_once()
        job = db.session.get(AnswerProcessingJob, self.job_id)
        question = db.session.get(InterviewQuestion, self.question_id)
        interview = db.session.get(Interview, self.interview_id)
        self.assertEqual(job.status, "NEEDS_REVIEW")
        self.assertEqual(job.outcome, "TEACHER_REVIEW")
        self.assertEqual(job.last_error_code, "invalid_evaluation_output")
        self.assertIsNone(question.content_score)
        self.assertEqual(interview.status, "COMPLETED")
        self.assertEqual(processing_summary(interview)["teacher_review"], 1)
        self.assertEqual(processing_summary(interview)["pending"], 0)
        self.assertIsNone(interview.report.final_score)

    def test_quota_exhaustion_is_terminal_without_worker_retry(self):
        self._prepare_evaluation_job()
        self.app.config["EVALUATION_MODE"] = "dual_sequential"
        storage = type("StorageStub", (), {"get": lambda _self, _key: b"saved audio"})()
        quota_failure = {
            "criteria_scores": {}, "content_score": None, "needs_teacher_review": True,
            "error_category": "quota_exhausted",
            "dual_model": {
                "retryable": False,
                "providers": {
                    "ollama": {"status": "SUCCESS", "evaluation": {"content_score": 8.0}},
                    "gemini": {"status": "FAILED", "error_category": "quota_exhausted", "retryable": False},
                },
            },
        }
        with (
            patch("queme.services.answer_jobs.get_storage", return_value=storage),
            patch("queme.services.answer_jobs.evaluate_interview_answer", return_value=quota_failure) as evaluate,
        ):
            run_worker(once=True)

        evaluate.assert_called_once()
        job = db.session.get(AnswerProcessingJob, self.job_id)
        self.assertEqual(job.status, "NEEDS_REVIEW")
        self.assertNotEqual(job.status, "RETRY_WAIT")
        self.assertEqual(job.last_error_code, "evaluation_unavailable")

    def test_transient_evaluation_infrastructure_error_remains_retryable(self):
        self._prepare_evaluation_job()
        storage = type("StorageStub", (), {"get": lambda _self, _key: b"saved audio"})()
        unavailable = {
            "criteria_scores": {}, "content_score": None, "needs_teacher_review": True,
            "error": "Local Ollama connection to http://localhost:11434 failed.",
        }
        with (
            patch("queme.services.answer_jobs.get_storage", return_value=storage),
            patch("queme.services.answer_jobs.evaluate_interview_answer", return_value=unavailable),
        ):
            run_worker(once=True)
        job = db.session.get(AnswerProcessingJob, self.job_id)
        interview = db.session.get(Interview, self.interview_id)
        self.assertEqual(job.status, "RETRY_WAIT")
        self.assertEqual(job.last_error_code, "ollama_unavailable")
        self.assertEqual(interview.status, "PROCESSING")
        self.assertEqual(processing_summary(interview)["retryable_failures"], 1)

    def test_worker_does_not_retry_infrastructure_error_after_soft_budget(self):
        self._prepare_evaluation_job()
        self.app.config["OLLAMA_EVALUATION_BUDGET_SECONDS"] = 1
        storage = type("StorageStub", (), {"get": lambda _self, _key: b"saved audio"})()
        unavailable = {
            "criteria_scores": {}, "content_score": None, "needs_teacher_review": True,
            "error": "Local Ollama connection to http://localhost:11434 failed.",
        }
        with (
            patch("queme.services.answer_jobs.get_storage", return_value=storage),
            patch("queme.services.answer_jobs.evaluate_interview_answer", return_value=unavailable),
            patch("queme.services.answer_jobs.time.monotonic", side_effect=[0, 2, 2]),
        ):
            run_worker(once=True)
        job = db.session.get(AnswerProcessingJob, self.job_id)
        self.assertEqual(job.status, "NEEDS_REVIEW")
        self.assertEqual(job.last_error_code, "evaluation_budget_exceeded")

    def test_unverified_evidence_keeps_valid_score_and_marks_teacher_review(self):
        self._prepare_evaluation_job()
        storage = type("StorageStub", (), {"get": lambda _self, _key: b"saved audio"})()

        def evaluated_with_unverified_evidence(question, *, correlation_id=None):
            question.content_score = 6.5
            question.delivery_score = 7.0
            question.final_ai_score = 6.65
            question.needs_review = True
            question.evaluation_json = {
                "content_score": 6.5,
                "criteria_scores": {"Correctness": 6.5},
                "needs_teacher_review": True,
                "review_reason": "evidence_unavailable",
                "evaluation_status": "COMPLETED",
            }
            return question.evaluation_json

        with (
            patch("queme.services.answer_jobs.get_storage", return_value=storage),
            patch("queme.services.answer_jobs.evaluate_interview_answer", side_effect=evaluated_with_unverified_evidence),
        ):
            run_worker(once=True)
        question = db.session.get(InterviewQuestion, self.question_id)
        job = db.session.get(AnswerProcessingJob, self.job_id)
        self.assertEqual(float(question.content_score), 6.5)
        self.assertEqual(float(question.final_ai_score), 6.65)
        self.assertTrue(question.needs_review)
        self.assertEqual(question.evaluation_json["evaluation_status"], "COMPLETED")
        self.assertEqual(job.status, "NEEDS_REVIEW")
        self.assertEqual(job.last_error_code, "evidence_unavailable")


if __name__ == "__main__":
    unittest.main()
