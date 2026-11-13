import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from queme import create_app
from queme.authz import make_token
from queme.extensions import db
from queme.models import (
    Interview,
    InterviewQuestion,
    InterviewTemplate,
    QuestionBank,
    User,
)
from queme.services.reports import build_improvement_plan, evaluate_interview_answer, generate_interview_report, summarize_interview_audio
from queme.services.reports import build_analysis_coverage
from queme.models import AudioAnalysis
from queme.services.audio_analysis import detect_intent
from queme.services.llm import evaluate_answer
from queme.blueprints.teacher import _rubric_criteria
from queme.blueprints.session import _adaptive_target_difficulty


class InterviewFlowTests(unittest.TestCase):
    def setUp(self):
        self.storage_dir = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret-key-that-is-long-enough-for-tests",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "FRONTEND_ORIGIN": "http://localhost:5173",
            "JWT_EXP_HOURS": 24,
            "STORAGE_BACKEND": "local",
            "STORAGE_LOCAL_DIR": Path(self.storage_dir.name),
            "OLLAMA_BASE_URL": "",
        })
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.student = User(full_name="Student", email="student@example.test", password_hash="x", role="student", account_status="ACTIVE")
        self.teacher = User(full_name="Teacher", email="teacher@example.test", password_hash="x", role="teacher", account_status="ACTIVE")
        self.admin = User(full_name="Admin", email="admin@example.test", password_hash="x", role="admin", account_status="ACTIVE")
        db.session.add_all([self.student, self.teacher, self.admin])
        db.session.flush()

        self.template = InterviewTemplate(title="Practice", created_by=self.teacher.user_id)
        self.question_one = QuestionBank(
            created_by=self.teacher.user_id,
            question_text="Explain normalization.",
            question_type="technical",
            difficulty="medium",
        )
        self.question_two = QuestionBank(
            created_by=self.teacher.user_id,
            question_text="What is a primary key?",
            question_type="technical",
            difficulty="easy",
        )
        db.session.add_all([self.template, self.question_one, self.question_two])
        db.session.flush()
        self.interview = Interview(
            student_id=self.student.user_id,
            teacher_id=self.teacher.user_id,
            template_id=self.template.template_id,
            status="SCHEDULED",
            consent_given=False,
            current_index=0,
        )
        db.session.add(self.interview)
        db.session.flush()
        self.first = InterviewQuestion(
            interview_id=self.interview.interview_id,
            question_id=self.question_one.question_id,
            question_order=1,
            is_followup=False,
        )
        self.second = InterviewQuestion(
            interview_id=self.interview.interview_id,
            question_id=self.question_two.question_id,
            question_order=2,
            is_followup=False,
        )
        db.session.add_all([self.first, self.second])
        db.session.commit()

        self.client = self.app.test_client()
        self.student_headers = self.headers(self.student)
        self.teacher_headers = self.headers(self.teacher)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        self.storage_dir.cleanup()

    @staticmethod
    def headers(user):
        return {"Authorization": f"Bearer {make_token(user)}"}

    def start_interview(self):
        return self.client.post(
            f"/api/interviews/{self.interview.interview_id}/start",
            json={"consent": True},
            headers=self.student_headers,
        )

    def test_registration_is_pending_and_pending_login_is_blocked(self):
        response = self.client.post("/api/auth/register", json={
            "full_name": "New Student",
            "email": "new-student@example.test",
            "password": "long-enough-password",
            "role": "student",
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["user"]["account_status"], "PENDING")

        login = self.client.post("/api/auth/login", json={
            "email": "new-student@example.test",
            "password": "long-enough-password",
        })
        self.assertEqual(login.status_code, 403)
        self.assertEqual(login.json["code"], "account_not_active")

    def test_rapidfire_questions_are_student_scoped_and_do_not_expose_rubrics(self):
        response = self.client.get("/api/rapidfire/questions", headers=self.student_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["question_id"] for row in response.json}, {
            self.question_one.question_id,
            self.question_two.question_id,
        })
        self.assertTrue(all("expected_key_points" not in row for row in response.json))
        self.assertEqual(self.client.get("/api/rapidfire/questions").status_code, 401)
        self.assertEqual(self.client.get("/api/rapidfire/questions", headers=self.teacher_headers).status_code, 403)

    def test_consent_is_required_and_unauthed_session_is_denied(self):
        denied = self.client.get(f"/api/interviews/{self.interview.interview_id}")
        self.assertEqual(denied.status_code, 401)

        no_consent = self.client.post(
            f"/api/interviews/{self.interview.interview_id}/start",
            json={"consent": False},
            headers=self.student_headers,
        )
        self.assertEqual(no_consent.status_code, 400)
        self.assertEqual(no_consent.json["code"], "consent_required")

        started = self.start_interview()
        self.assertEqual(started.status_code, 200)
        self.assertIsNotNone(self.first.asked_at)

    def test_skip_advances_and_repeat_does_not_advance(self):
        self.start_interview()
        repeat = self.client.post(
            f"/api/interviews/{self.interview.interview_id}/advance",
            json={"intent": "REPEAT"},
            headers=self.student_headers,
        )
        self.assertEqual(repeat.json["action"], "repeat")
        self.assertEqual(repeat.json["session"]["current_index"], 0)

        skipped = self.client.post(
            f"/api/interviews/{self.interview.interview_id}/advance",
            json={"intent": "SKIP"},
            headers=self.student_headers,
        )
        self.assertEqual(skipped.status_code, 200)
        self.assertEqual(skipped.json["session"]["current_index"], 1)
        self.assertIsNotNone(self.second.asked_at)

    def test_report_override_sets_final_score_for_assigned_teacher(self):
        self.interview.status = "COMPLETED"
        report = generate_interview_report(self.interview)
        db.session.commit()
        self.assertIsNotNone(report)

        response = self.client.patch(
            f"/api/interviews/{self.interview.interview_id}/report",
            json={"teacher_score": 8.25, "teacher_remark": "Reviewed."},
            headers=self.teacher_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["final_score"], 8.25)
        self.assertEqual(response.json["score_source"], "TEACHER")

    def test_adaptive_answer_uses_only_completed_scores_and_never_moves_selected_questions(self):
        harder_question = QuestionBank(
            created_by=self.teacher.user_id,
            question_text="Explain a Python generator.",
            question_type="technical",
            difficulty="hard",
        )
        medium_question = QuestionBank(
            created_by=self.teacher.user_id,
            question_text="Explain Python decorators.",
            question_type="technical",
            difficulty="medium",
        )
        db.session.add_all([harder_question, medium_question])
        db.session.flush()
        harder_row = InterviewQuestion(
            interview_id=self.interview.interview_id,
            question_id=harder_question.question_id,
            question_order=3,
            is_followup=False,
        )
        medium_row = InterviewQuestion(
            interview_id=self.interview.interview_id,
            question_id=medium_question.question_id,
            question_order=4,
            is_followup=False,
        )
        db.session.add_all([harder_row, medium_row])
        db.session.commit()
        self.start_interview()
        storage = type("StorageStub", (), {"put": lambda _self, key, _data, content_type: key})()
        answer_url = f"/api/interviews/{self.interview.interview_id}/questions/{self.first.interview_question_id}/answer"
        with patch("queme.services.answer_jobs.transcribe") as transcribe_answer, patch(
            "queme.blueprints.session.get_storage", return_value=storage
        ):
            response = self.client.post(
                answer_url,
                data={"audio": (io.BytesIO(b"fake audio"), "answer.webm", "audio/webm")},
                headers=self.student_headers,
            )
        transcribe_answer.assert_not_called()

        self.assertEqual(response.status_code, 200, response.json)
        session = response.json["session"]
        self.assertEqual(session["total_questions"], 4)
        self.assertEqual(session["current_index"], 1)
        self.assertEqual(session["current_question"]["question_id"], self.question_two.question_id)
        self.assertEqual(session["answer_processing"]["pending"], 1)
        self.assertEqual(self.first.processing_job.status, "QUEUED")

        # A late evaluation cannot reorder the question already selected for the student.
        self.first.content_score = 9.0
        self.first.final_ai_score = 8.4
        self.first.processing_job.status = "COMPLETED"
        self.first.processing_job.outcome = "EVALUATED"
        self.first.processing_job.finished_at = datetime.utcnow()
        db.session.commit()

        with patch("queme.blueprints.session.get_storage", return_value=storage):
            next_response = self.client.post(
                f"/api/interviews/{self.interview.interview_id}/questions/{self.second.interview_question_id}/answer",
                data={"audio": (io.BytesIO(b"next audio"), "answer.webm", "audio/webm")},
                headers=self.student_headers,
            )
        self.assertEqual(next_response.status_code, 200, next_response.json)
        self.assertEqual(next_response.json["session"]["current_question"]["question_id"], harder_question.question_id)

        ordered = InterviewQuestion.query.filter_by(interview_id=self.interview.interview_id).order_by(
            InterviewQuestion.question_order
        ).all()
        self.assertEqual([row.question_id for row in ordered], [
            self.question_one.question_id,
            self.question_two.question_id,
            harder_question.question_id,
            medium_question.question_id,
        ])
        self.assertFalse(any(row.is_followup for row in ordered))
        self.assertIsNotNone(ordered[1].asked_at)
        self.assertIn(f"questions/{self.first.interview_question_id}/answers/", ordered[0].answer_audio_path)

    def test_adaptive_thresholds_use_the_normalized_ten_point_content_scale(self):
        with self.app.app_context():
            self.assertEqual(_adaptive_target_difficulty("easy", 9.0), "medium")
            self.assertEqual(_adaptive_target_difficulty("medium", 4.5), "easy")
            self.assertEqual(_adaptive_target_difficulty("medium", 6.5), "medium")
            self.assertEqual(_adaptive_target_difficulty("hard", 10.0), "hard")
            self.assertEqual(_adaptive_target_difficulty("easy", None), "easy")

    def test_answer_submission_is_durable_idempotent_and_does_not_wait(self):
        self.start_interview()
        stored = {}
        puts = []

        class StorageStub:
            def put(self, key, data, content_type=None):
                puts.append(key)
                stored[key] = data
                return key

            def delete(self, key):
                stored.pop(key, None)

        answer_url = f"/api/interviews/{self.interview.interview_id}/questions/{self.first.interview_question_id}/answer"
        submission_id = "ef932d5a-26cb-4fb7-a0a0-5860672bfb27"
        data = {
            "submission_id": submission_id,
            "audio": (io.BytesIO(b"first recording"), "answer.webm", "audio/webm"),
        }
        with patch("queme.services.answer_jobs.transcribe") as transcription, patch(
            "queme.blueprints.session.get_storage", return_value=StorageStub()
        ):
            accepted = self.client.post(answer_url, data=data, headers=self.student_headers)
            self.assertEqual(accepted.status_code, 200, accepted.json)
            self.assertEqual(accepted.json["action"], "next")
            self.assertEqual(accepted.json["session"]["current_index"], 1)
            self.assertEqual(accepted.json["session"]["answer_processing"]["pending"], 1)
            self.assertEqual(self.first.processing_job.status, "QUEUED")
            transcription.assert_not_called()

            duplicate = self.client.post(
                answer_url,
                data={
                    "submission_id": submission_id,
                    "audio": (io.BytesIO(b"duplicate body"), "answer.webm", "audio/webm"),
                },
                headers=self.student_headers,
            )
            self.assertEqual(duplicate.status_code, 200, duplicate.json)
            self.assertTrue(duplicate.json["idempotent_replay"])
            self.assertEqual(len(puts), 1)
            self.assertEqual(next(iter(stored.values())), b"first recording")

            conflict = self.client.post(
                answer_url,
                data={
                    "submission_id": "ca640215-4212-4540-9eeb-e48b1e7c4470",
                    "audio": (io.BytesIO(b"replacement"), "answer.webm", "audio/webm"),
                },
                headers=self.student_headers,
            )
            self.assertEqual(conflict.status_code, 409)
            self.assertEqual(len(puts), 1)

        self.assertIn(f"questions/{self.first.interview_question_id}/answers/{submission_id}", self.first.answer_audio_path)
        self.assertEqual(self.first.processing_job.audio_path, self.first.answer_audio_path)

    def test_audio_summary_uses_saved_usable_recordings_and_skips_invalid_values(self):
        questions = [
            SimpleNamespace(
                answer_audio_path="saved-audio.webm",
                analysis=SimpleNamespace(
                    audio_usable=True,
                    audio_quality_status="OK",
                    transcript="one two three four five",
                    words_per_minute=120,
                    pause_count=2,
                    filler_word_count=1,
                    delivery_score=7,
                ),
            ),
            SimpleNamespace(
                answer_audio_path="saved-audio-2.webm",
                analysis=SimpleNamespace(
                    audio_usable=True,
                    audio_quality_status="OK",
                    transcript="another answer with several spoken words",
                    words_per_minute=float("nan"),
                    pause_count=None,
                    filler_word_count=-1,
                    delivery_score=11,
                ),
            ),
            SimpleNamespace(
                answer_audio_path="poor-audio.webm",
                analysis=SimpleNamespace(
                    audio_usable=False,
                    words_per_minute=90,
                    pause_count=4,
                    filler_word_count=3,
                    delivery_score=5,
                ),
            ),
            SimpleNamespace(
                answer_audio_path=None,
                analysis=SimpleNamespace(
                    audio_usable=True,
                    words_per_minute=60,
                    pause_count=1,
                    filler_word_count=0,
                    delivery_score=8,
                ),
            ),
        ]
        self.assertEqual(summarize_interview_audio(questions), {
            "questions_included": 2,
            "averages": {
                "words_per_minute": 120.0,
                "pause_count": 2.0,
                "total_pause_duration_seconds": None,
                "longest_pause_seconds": None,
                "filler_word_count": 1.0,
                "delivery_score": 7.0,
                "fillers_per_100_words": 20.0,
            },
            "metric_sample_counts": {
                "words_per_minute": 1,
                "pause_count": 1,
                "total_pause_duration_seconds": 0,
                "longest_pause_seconds": 0,
                "filler_word_count": 1,
                "delivery_score": 1,
                "fillers_per_100_words": 1,
            },
            "words_per_minute": 120.0,
            "total_pause_duration_seconds": None,
            "longest_pause_seconds": None,
            "pause_count": 2.0,
            "filler_word_count": 1.0,
            "delivery_score": 7.0,
            "fillers_per_100_words": 20.0,
            "filler_word_denominator": 5,
        })

    def test_weighted_rubric_validation_and_evidence_grounding(self):
        weighted, error = _rubric_criteria({"criteria": [
            {"name": "Correctness", "weight": 80},
            {"name": "Structure", "weight": 20},
        ]})
        self.assertIsNone(error)
        self.assertEqual([item["weight"] for item in weighted["criteria"]], [80, 20])
        self.assertIsNotNone(_rubric_criteria({"criteria": [
            {"name": "Correctness", "weight": 80},
            {"name": "Structure", "weight": 10},
        ]})[1])

        response = {
            "criteria_scores": {"Correctness": 10, "Structure": 0},
            "criterion_details": {
                "Correctness": {"applicable": True, "explanation": "Defined SQL accurately.", "evidence": "SQL manages data"},
                "Structure": {"applicable": True, "explanation": "No sequence was stated.", "evidence": "invented quote"},
            },
            "technical_accuracy": "Partially accurate.", "missing_concepts": [],
            "correct_explanation": "A useful answer explains the concept clearly.",
            "strengths": [], "weaknesses": [], "feedback": "Keep practising.",
            "needs_teacher_review": False,
        }
        with patch("queme.services.llm._configured", return_value=True), patch(
            "queme.services.llm._generate", return_value=json.dumps(response)
        ):
            evaluated = evaluate_answer({
                "transcript": "SQL manages data",
                "rubric": {"criteria": [{"name": "Correctness", "weight": 80}, {"name": "Structure", "weight": 20}]},
            })
        self.assertEqual(evaluated["content_score"], 8.0)
        self.assertEqual(evaluated["criteria_weights"], {"Correctness": 80.0, "Structure": 20.0})
        self.assertEqual(evaluated["criterion_details"]["Correctness"]["evidence"], "SQL manages data")
        self.assertIsNone(evaluated["criterion_details"]["Structure"]["evidence"])
        self.assertTrue(evaluated["needs_teacher_review"])

    def test_improvement_plan_deduplicates_repeated_criterion_areas(self):
        self.first.transcript = "I used a list."
        self.first.evaluation_json = {
            "criteria_scores": {"Correctness": 5},
            "criterion_details": {"Correctness": {"applicable": True, "explanation": "Add precision.", "evidence": "I used a list."}},
        }
        self.second.transcript = "A list stores items."
        self.second.evaluation_json = {
            "criteria_scores": {" correctness ": 3},
            "criterion_details": {" correctness ": {"applicable": True, "explanation": "Explain behavior.", "evidence": "A list stores items."}},
        }
        plan = build_improvement_plan([self.first, self.second], [], {})
        repeated = [item for item in plan if item["area"].strip().casefold() == "correctness"]
        self.assertEqual(len(repeated), 1)
        self.assertEqual(repeated[0]["score"], 3)

    def test_empty_analysis_coverage_is_unavailable_not_zero_percent(self):
        coverage = build_analysis_coverage([])
        self.assertEqual(coverage["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(coverage["coverage"]["overall"]["percentage"])

    def test_queued_answers_finalize_report_only_after_worker_processing(self):
        from queme.services.answer_jobs import run_worker

        self.start_interview()
        interview_id = self.interview.interview_id
        audio_objects = {}
        recording_metrics = iter((
            {"audio_usable": True, "audio_quality_status": "OK", "delivery_score": 7.0,
             "words_per_minute": 120, "pause_count": 2, "filler_word_count": 1,
             "analysis_json": {"word_timestamps": []}},
            {"audio_usable": True, "audio_quality_status": "OK", "delivery_score": 9.0,
             "words_per_minute": 90, "pause_count": 4, "filler_word_count": 3,
             "analysis_json": {"word_timestamps": []}},
        ))

        class StorageStub:
            def put(self, key, data, content_type=None):
                audio_objects[key] = data
                return key

            def get(self, key):
                return audio_objects[key]

            def delete(self, key):
                audio_objects.pop(key, None)

        storage = StorageStub()
        with patch("queme.blueprints.session.get_storage", return_value=storage):
            first_response = self.client.post(
                f"/api/interviews/{self.interview.interview_id}/questions/{self.first.interview_question_id}/answer",
                data={"audio": (io.BytesIO(b"first audio"), "first.webm", "audio/webm")},
                headers=self.student_headers,
            )
            self.assertEqual(first_response.status_code, 200, first_response.json)
            second_response = self.client.post(
                f"/api/interviews/{self.interview.interview_id}/questions/{self.second.interview_question_id}/answer",
                data={"audio": (io.BytesIO(b"second audio"), "second.webm", "audio/webm")},
                headers=self.student_headers,
            )

        self.assertEqual(second_response.status_code, 200, second_response.json)
        self.assertEqual(second_response.json["action"], "processing")
        self.assertEqual(db.session.get(Interview, interview_id).status, "PROCESSING")
        self.assertEqual(
            self.client.get(f"/api/interviews/{interview_id}/report", headers=self.student_headers).status_code,
            409,
        )

        def score_answer(question, *, correlation_id=None):
            self.assertEqual(correlation_id, f"answer_job:{question.processing_job.job_id}")
            question.content_score = 8.0
            question.delivery_score = float(question.analysis.delivery_score)
            question.final_ai_score = round(0.7 * question.content_score + 0.3 * question.delivery_score, 2)
            question.needs_review = False
            question.evaluation_json = {"needs_teacher_review": False}
            return question.evaluation_json

        self.app.instance_path = self.storage_dir.name
        with (
            patch("queme.services.answer_jobs.get_storage", return_value=storage),
            patch("queme.services.answer_jobs.transcribe", return_value={"transcript": "A clear answer.", "words": [], "status": "OK"}),
            patch("queme.services.answer_jobs.analyze_audio", side_effect=lambda *_args, **_kwargs: next(recording_metrics)),
            patch("queme.services.answer_jobs.evaluate_interview_answer", side_effect=score_answer),
        ):
            run_worker(once=True)
            self.assertEqual(db.session.get(Interview, interview_id).status, "PROCESSING")
            run_worker(once=True)

        self.assertEqual(db.session.get(Interview, interview_id).status, "COMPLETED")
        report_response = self.client.get(
            f"/api/interviews/{interview_id}/report",
            headers=self.student_headers,
        )
        self.assertEqual(report_response.status_code, 200, report_response.json)
        report = report_response.json
        self.assertEqual(report["answer_processing"]["successfully_evaluated"], 2)
        self.assertEqual(report["answer_processing"]["pending"], 0)
        self.assertEqual(report["answer_processing"]["retryable_failures"], 0)
        self.assertEqual(report["answer_processing"]["teacher_review"], 0)
        audio_summary = report["audio_summary"]
        self.assertEqual(audio_summary["questions_included"], 2)
        self.assertEqual(audio_summary["words_per_minute"], 105.0)
        self.assertEqual(audio_summary["pause_count"], 3.0)
        self.assertEqual(audio_summary["filler_word_count"], 2.0)
        self.assertEqual(audio_summary["delivery_score"], 8.0)
        self.assertEqual(report["analysis_coverage"]["coverage"]["overall"]["percentage"], 100.0)
        self.assertEqual([row["final_ai_score"] for row in report["questions"]], [7.7, 8.3])
        self.assertTrue(all(row["processing_status"] == "SUCCESSFULLY_EVALUATED" for row in report["questions"]))
        pdf_response = self.client.get(
            f"/api/interviews/{interview_id}/report.pdf",
            headers=self.student_headers,
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertTrue(pdf_response.data.startswith(b"%PDF-"))

    def test_audio_metrics_are_included_in_evaluation_payload(self):
        analysis = AudioAnalysis(
            interview_question_id=self.first.interview_question_id,
            transcript="A concise answer.",
            transcription_status="OK",
            answer_duration_seconds=12.5,
            speaking_duration_seconds=10.0,
            words_per_minute=96.0,
            pause_count=2,
            total_pause_duration_seconds=1.3,
            longest_pause_seconds=0.8,
            filler_word_count=1,
            filler_word_rate=0.1,
            repetition_count=0,
            speech_ratio=0.8,
            audio_quality_status="OK",
            delivery_score=7.0,
        )
        db.session.add(analysis)
        db.session.flush()
        captured = {}

        def fake_evaluate(payload):
            captured.update(payload)
            return {"criteria_scores": {}, "content_score": None, "needs_teacher_review": True}

        with patch("queme.services.reports.evaluate_answer", side_effect=fake_evaluate):
            evaluate_interview_answer(self.first)

        self.assertEqual(captured["audio_metrics"]["words_per_minute"], 96.0)
        self.assertEqual(captured["audio_metrics"]["pause_count"], 2)
        json.dumps(captured)

    def test_voice_intents_only_match_whole_commands(self):
        self.assertEqual(detect_intent("Could you repeat that?"), "REPEAT")
        self.assertEqual(detect_intent("I will pass the data to the next function."), "ANSWER")
        self.assertEqual(detect_intent("Let me explain, then I am done."), "ANSWER")
        self.assertEqual(detect_intent("Skip this question."), "SKIP")


if __name__ == "__main__":
    unittest.main()
