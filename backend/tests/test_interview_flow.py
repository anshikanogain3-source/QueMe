import io
import json
import tempfile
import unittest
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
from queme.services.reports import evaluate_interview_answer, generate_interview_report, summarize_interview_audio
from queme.services.reports import build_analysis_coverage
from queme.models import AudioAnalysis
from queme.services.audio_analysis import detect_intent
from queme.services.llm import evaluate_answer
from queme.blueprints.teacher import _rubric_criteria


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

    def test_usable_answer_inserts_followup_before_remaining_questions(self):
        self.start_interview()
        metrics = {
            "detected_intent": "ANSWER",
            "audio_usable": True,
            "audio_quality_status": "OK",
            "delivery_score": 7.0,
            "analysis_json": {"word_timestamps": []},
        }
        storage = type("StorageStub", (), {"put": lambda _self, key, _data, content_type: key})()
        with (
            patch("queme.blueprints.session.transcribe", return_value={"transcript": "A concise answer.", "words": [], "status": "OK"}),
            patch("queme.blueprints.session.analyze_audio", return_value=metrics),
            patch("queme.blueprints.session.evaluate_interview_answer"),
            patch("queme.blueprints.session.generate_followup", return_value="Can you give an example?"),
            patch("queme.blueprints.session.get_storage", return_value=storage),
        ):
            response = self.client.post(
                f"/api/interviews/{self.interview.interview_id}/questions/{self.first.interview_question_id}/answer",
                data={"audio": (io.BytesIO(b"fake audio"), "answer.webm", "audio/webm")},
                headers=self.student_headers,
            )

        self.assertEqual(response.status_code, 200, response.json)
        session = response.json["session"]
        self.assertEqual(session["total_questions"], 3)
        self.assertEqual(session["current_index"], 1)
        self.assertTrue(session["current_question"]["is_followup"])
        self.assertEqual(session["current_question"]["question_text"], "Can you give an example?")

        ordered = InterviewQuestion.query.filter_by(interview_id=self.interview.interview_id).order_by(InterviewQuestion.question_order).all()
        self.assertEqual([row.question_order for row in ordered], [1, 2, 3])
        self.assertTrue(ordered[1].is_followup)
        self.assertIsNotNone(ordered[1].asked_at)
        self.assertEqual(ordered[2].question_id, self.question_two.question_id)
        self.assertIn(f"questions/{self.first.interview_question_id}/answer.webm", ordered[0].answer_audio_path)

        skipped = self.client.post(
            f"/api/interviews/{self.interview.interview_id}/advance",
            json={"intent": "SKIP"},
            headers=self.student_headers,
        )
        self.assertEqual(skipped.status_code, 200)
        self.assertEqual(skipped.json["session"]["current_index"], 2)
        self.assertEqual(skipped.json["session"]["current_question"]["question_text"], "What is a primary key?")

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
            "strengths": [], "weaknesses": [], "feedback": "Keep practising.",
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

    def test_empty_analysis_coverage_is_unavailable_not_zero_percent(self):
        coverage = build_analysis_coverage([])
        self.assertEqual(coverage["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(coverage["coverage"]["overall"]["percentage"])

    def test_recording_to_completed_report_and_pdf(self):
        self.start_interview()
        recording_metrics = iter((
            {"audio_usable": True, "audio_quality_status": "OK", "delivery_score": 7.0,
             "words_per_minute": 120, "pause_count": 2, "filler_word_count": 1,
             "analysis_json": {"word_timestamps": []}},
            {"audio_usable": True, "audio_quality_status": "OK", "delivery_score": 9.0,
             "words_per_minute": 90, "pause_count": 4, "filler_word_count": 3,
             "analysis_json": {"word_timestamps": []}},
        ))
        storage = type("StorageStub", (), {"put": lambda _self, key, _data, content_type=None: key})()

        def score_answer(question):
            question.transcript = question.analysis.transcript
            question.content_score = 8.0
            question.delivery_score = float(question.analysis.delivery_score)
            question.final_ai_score = round(0.7 * question.content_score + 0.3 * question.delivery_score, 2)
            question.needs_review = False
            question.evaluation_json = {"needs_teacher_review": False}

        with (
            patch("queme.blueprints.session.transcribe", return_value={"transcript": "A clear answer.", "words": [], "status": "OK"}),
            patch("queme.blueprints.session.analyze_audio", side_effect=lambda *_args, **_kwargs: next(recording_metrics)),
            patch("queme.blueprints.session.evaluate_interview_answer", side_effect=score_answer),
            patch("queme.blueprints.session.generate_followup", return_value=None),
            patch("queme.blueprints.session.get_storage", return_value=storage),
        ):
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
        self.assertEqual(second_response.json["action"], "complete")
        report_response = self.client.get(
            f"/api/interviews/{self.interview.interview_id}/report",
            headers=self.student_headers,
        )
        self.assertEqual(report_response.status_code, 200, report_response.json)
        audio_summary = report_response.json["audio_summary"]
        self.assertEqual(audio_summary["questions_included"], 2)
        self.assertEqual(audio_summary["words_per_minute"], 105.0)
        self.assertEqual(audio_summary["pause_count"], 3.0)
        self.assertEqual(audio_summary["filler_word_count"], 2.0)
        self.assertEqual(audio_summary["delivery_score"], 8.0)
        self.assertEqual(audio_summary, report_response.json["audio_summary"])
        self.assertEqual(report_response.json["analysis_coverage"]["coverage"]["overall"]["percentage"], 100.0)
        self.assertEqual([row["final_ai_score"] for row in report_response.json["questions"]], [7.7, 8.3])
        pdf_response = self.client.get(
            f"/api/interviews/{self.interview.interview_id}/report.pdf",
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
