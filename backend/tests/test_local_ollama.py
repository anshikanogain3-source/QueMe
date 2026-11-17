import io
import json
import socket
import sys
import tempfile
import types as python_types
import unittest
from types import SimpleNamespace
from urllib.error import URLError
from unittest.mock import patch
from unittest.mock import Mock
from google.genai.errors import APIError

from queme import create_app
from queme.services.llm import _check_model_available, _evaluation_token_budget, _failure_is_retryable, _generate, _generate_json, _ollama_process_lock, _provider_error_category, evaluate_answer, generate_followup, generate_questions
from queme.services.reports import _compare_dual_evaluations, evaluate_interview_answer


class LocalOllamaTests(unittest.TestCase):
    def setUp(self):
        self.instance_dir = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret-key-that-is-long-enough-for-tests",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "STORAGE_BACKEND": "local",
            "JWT_EXP_HOURS": 24,
            "FRONTEND_ORIGIN": "http://localhost:5173",
            "OLLAMA_BASE_URL": "http://localhost:11434",
            "OLLAMA_MODEL": "qwen3:1.7b",
            "EVALUATION_MODE": "single_provider",
            "EVALUATION_PROVIDER": "ollama",
            "OLLAMA_KEEP_ALIVE": "30m",
            "OLLAMA_TIMEOUT": 120,
            "OLLAMA_TEMPERATURE": 0.2,
            "OLLAMA_NUM_CTX": 4096,
        })
        self.app.instance_path = self.instance_dir.name
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        self.instance_dir.cleanup()

    def _mock_google_sdk(self, response_text=None, side_effect=None):
        response = Mock(text=response_text)
        client = Mock()
        client.models.generate_content.side_effect = side_effect or [response]
        genai_module = python_types.ModuleType("google.genai")
        genai_module.Client = Mock(return_value=client)
        types_module = python_types.ModuleType("google.genai.types")
        types_module.HttpOptions = Mock(side_effect=lambda **kwargs: kwargs)
        types_module.HttpRetryOptions = Mock(side_effect=lambda **kwargs: kwargs)
        types_module.GenerateContentConfig = Mock(side_effect=lambda **kwargs: kwargs)
        google_module = python_types.ModuleType("google")
        google_module.__path__ = []
        google_module.genai = genai_module
        genai_module.__path__ = []
        genai_module.types = types_module
        modules = {
            "google": google_module,
            "google.genai": genai_module,
            "google.genai.types": types_module,
        }
        return modules, client, genai_module, types_module

    @staticmethod
    def _google_api_error(code, message, details=None):
        return APIError(code, {"error": {
            "code": code,
            "message": message,
            "status": "RESOURCE_EXHAUSTED" if code == 429 else "PERMISSION_DENIED",
            "details": details or [],
        }})

    @staticmethod
    def _gemini_answer(score=8, evidence="The list can change after creation.", supports=True):
        return {
            "criteria_scores": {"Overall": score},
            "criterion_details": {"Overall": {
                "applicable": True,
                "explanation": "The answer states that a list can be changed.",
                "evidence": evidence,
                "evidence_supports_claim": supports,
                "evidence_explanation": "This sentence directly states the claimed behavior." if supports else "This excerpt does not support the claim.",
            }},
            "question_relevant": True,
            "relevance_explanation": "The answer describes the behavior asked about.",
            "accuracy_category": "MOSTLY_CORRECT_INCOMPLETE",
            "technical_accuracy": "Mostly accurate.", "missing_concepts": ["An example"],
            "correct_explanation": "A list can be modified after it is created.",
            "strengths": ["Identified mutability."], "weaknesses": ["No example."],
            "feedback": "Add an example.", "needs_teacher_review": False,
            "incorrect_claims": [], "correct_concepts": ["mutability"],
            "suggested_improvements": ["Add an example."], "completeness": "INCOMPLETE",
        }

    @staticmethod
    def _serialized_model_answer(answer):
        return json.dumps({
            "incorrect_claims": [], "correct_concepts": ["relevant concept"],
            "suggested_improvements": [], "completeness": "INCOMPLETE", **answer,
        })

    def test_chat_request_uses_local_endpoint_and_configured_controls(self):
        response = io.BytesIO(json.dumps({
            "message": {"content": "{\"ok\":true}"},
            "load_duration": 1_000_000,
            "prompt_eval_duration": 2_000_000,
            "eval_duration": 4_000_000_000,
            "total_duration": 4_003_000_000,
            "prompt_eval_count": 20,
            "eval_count": 4,
        }).encode())
        response.__enter__ = lambda: response
        response.__exit__ = lambda *_args: None
        with patch("queme.services.llm.urlopen", return_value=response) as urlopen:
            with self.assertLogs("queme.services.llm", level="INFO") as captured:
                self.assertEqual(_generate(
                    "return JSON", num_predict=55,
                    operation="answer_evaluation", correlation_id="answer_job:42",
                ), '{"ok":true}')
        timing_logs = "\n".join(captured.output)
        self.assertIn("Ollama lock wait started", timing_logs)
        self.assertIn("Ollama lock acquired", timing_logs)
        self.assertIn("Ollama request started", timing_logs)
        self.assertIn("Ollama request completed", timing_logs)
        self.assertIn("correlation_id=answer_job:42", timing_logs)
        self.assertIn("load_ms=1.0", timing_logs)
        self.assertIn("prompt_eval_ms=2.0", timing_logs)
        self.assertIn("generation_ms=4000.0", timing_logs)
        self.assertIn("generated_tokens=4", timing_logs)
        self.assertIn("tokens_per_second=1.0", timing_logs)
        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "http://localhost:11434/api/chat")
        self.assertEqual(body["model"], "qwen3:1.7b")
        self.assertFalse(body["think"])
        self.assertEqual(body["keep_alive"], "30m")
        self.assertEqual(body["options"], {"temperature": 0.2, "num_predict": 55, "num_ctx": 4096})
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 120)

    def test_model_check_uses_tags_and_requires_the_configured_model(self):
        response = io.BytesIO(json.dumps({"models": [{"name": "qwen3:1.7b"}]}).encode())
        with patch("queme.services.llm.urlopen", return_value=response) as urlopen:
            _check_model_available()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:11434/api/tags")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)

        response = io.BytesIO(json.dumps({"models": [{"name": "other-model:latest"}]}).encode())
        with patch("queme.services.llm.urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "qwen3:1.7b.*not installed"):
                _check_model_available()

    def test_model_check_reports_connection_and_timeout_errors(self):
        with patch("queme.services.llm.urlopen", side_effect=URLError(ConnectionRefusedError(111, "Connection refused"))):
            with self.assertRaisesRegex(RuntimeError, "Connection refused"):
                _check_model_available()

        with patch("queme.services.llm.urlopen", side_effect=URLError(socket.timeout("timed out"))):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                _check_model_available()

    def test_json_generation_retries_invalid_content_once(self):
        with patch("queme.services.llm._generate", side_effect=["not json", '{"followup":null}']) as generate:
            with self.assertLogs("queme.services.llm", level="WARNING") as captured:
                result = _generate_json(
                    "prompt", validator=lambda value: isinstance(value, dict),
                    operation="answer_evaluation", correlation_id="answer_job:42",
                )
        self.assertEqual(result, {"followup": None})
        self.assertEqual(generate.call_count, 2)
        self.assertIn("reason=invalid_json retrying=True", "\n".join(captured.output))

    def test_structured_repair_is_skipped_when_soft_budget_is_exhausted(self):
        with patch("queme.services.llm._generate", return_value="not json") as generate:
            with self.assertRaisesRegex(ValueError, "invalid structured content"):
                _generate_json("prompt", validator=lambda value: isinstance(value, dict), soft_budget_seconds=0)
        self.assertEqual(generate.call_count, 1)

    def test_evaluation_token_budget_scales_with_rubric_and_is_bounded(self):
        self.assertEqual(_evaluation_token_budget(1), 755)
        self.assertGreater(_evaluation_token_budget(20), _evaluation_token_budget(1))
        self.assertEqual(_evaluation_token_budget(100), 1800)

    def test_shared_ollama_lock_wait_has_a_finite_timeout(self):
        self.app.config["OLLAMA_LOCK_WAIT_TIMEOUT"] = 1
        with patch("queme.services.llm.fcntl.flock", side_effect=BlockingIOError), patch(
            "queme.services.llm.time.monotonic", side_effect=[0, 1, 2]
        ):
            with self.assertRaisesRegex(TimeoutError, "inference lock"):
                with _ollama_process_lock(operation="answer_evaluation"):
                    self.fail("Lock should not have been acquired")

    def test_incomplete_rubric_output_fails_without_returning_partial_scores(self):
        incomplete = {
            "criteria_scores": {"Correctness": 8}, "criterion_details": {},
        }
        with patch("queme.services.llm._generate", return_value=json.dumps(incomplete)) as generate:
            result = evaluate_answer({
                "transcript": "Lists are mutable",
                "rubric": {"criteria": [{"name": "Correctness", "weight": 100}]},
            })
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result["criteria_scores"], {})
        self.assertIsNone(result["content_score"])
        self.assertTrue(result["needs_teacher_review"])
        self.assertIn("invalid structured content", result["error"])

    def test_twenty_criterion_custom_rubric_keeps_every_score_and_detail(self):
        names = [f"Criterion {index}" for index in range(1, 21)]
        answer = {
            "question_relevant": True, "relevance_explanation": "It answers the requested concept.", "accuracy_category": "MOSTLY_CORRECT_INCOMPLETE",
            "criteria_scores": {name: 7 for name in names},
            "criterion_details": {
                name: {"applicable": True, "explanation": "Relevant point.", "evidence": "It is a clear answer.", "evidence_supports_claim": True, "evidence_explanation": "This directly states the relevant point."}
                for name in names
            },
            "technical_accuracy": "Accurate.", "missing_concepts": [],
            "correct_explanation": "A clear answer demonstrates the concept.",
            "strengths": [], "weaknesses": [], "feedback": "Good work.",
            "needs_teacher_review": False,
        }
        payload = {
            "transcript": "It is a clear answer.",
            "rubric": {"criteria": [{"name": name, "weight": 5} for name in names]},
        }
        with patch("queme.services.llm._generate", return_value=self._serialized_model_answer(answer)) as generate:
            result = evaluate_answer(payload)
        self.assertEqual(generate.call_args.kwargs["num_predict"], 1800)
        self.assertEqual(set(result["criteria_scores"]), set(names))
        self.assertEqual(set(result["criterion_details"]), set(names))
        self.assertTrue(result["needs_teacher_review"])
        self.assertEqual(result["review_reason"], "semantic_support_requires_teacher_review")

    def test_evaluation_timeout_logs_timing_and_preserves_safe_error_result(self):
        answer_text = "private candidate answer text"
        payload = {
            "question": "A safe test question",
            "transcript": answer_text,
            "rubric": {"criteria": [{"name": "Correctness", "weight": 100}]},
        }
        timeout = URLError(socket.timeout("timed out"))
        with patch("queme.services.llm.urlopen", side_effect=timeout):
            with self.assertLogs("queme.services.llm", level="INFO") as captured:
                result = evaluate_answer(payload, correlation_id="answer_job:43")
        timing_logs = "\n".join(captured.output)
        self.assertIn("Answer evaluation started correlation_id=answer_job:43", timing_logs)
        self.assertIn("Ollama request started operation=answer_evaluation", timing_logs)
        self.assertIn("Ollama request timed out operation=answer_evaluation", timing_logs)
        self.assertIn("AI answer evaluation failed correlation_id=answer_job:43", timing_logs)
        self.assertNotIn(answer_text, timing_logs)
        self.assertIsNone(result["content_score"])
        self.assertTrue(result["needs_teacher_review"])
        self.assertIn("timed out", result["error"])

    def test_question_generation_returns_safe_error_when_ollama_is_unavailable(self):
        with patch("queme.services.llm._check_model_available"), patch("queme.services.llm._generate", side_effect=RuntimeError("Local Ollama connection failed.")):
            result = generate_questions("Python", "technical", "easy", count=2)
        self.assertFalse(result["available"])
        self.assertEqual(result["questions"], [])
        self.assertIn("Local Ollama", result["error"])

    def test_question_generation_accepts_qwen_single_object_json(self):
        response = {"question_text": "How do lists and tuples differ?", "question_type": "technical", "difficulty": "easy", "expected_key_points": ["mutable", "immutable"]}
        with patch("queme.services.llm._check_model_available"), patch("queme.services.llm._generate", return_value=json.dumps(response)):
            result = generate_questions("Python", "technical", "easy", count=1)
        self.assertTrue(result["available"])
        self.assertEqual(len(result["questions"]), 1)

    def test_i_dont_know_is_handled_without_a_model_call(self):
        with patch("queme.services.llm._generate") as generate:
            result = evaluate_answer({
                "transcript": "I don't know.",
                "rubric": {"criteria": [{"name": "Correctness", "weight": 100}]},
            })
        generate.assert_not_called()
        self.assertEqual(result["content_score"], 0.0)
        self.assertEqual(result["criteria_scores"], {"Correctness": 0.0})
        self.assertTrue(result["weaknesses"])

    def test_evaluation_returns_validated_learning_feedback(self):
        answer = {
            "question_relevant": True, "relevance_explanation": "It answers the question.", "accuracy_category": "MOSTLY_CORRECT_INCOMPLETE",
            "criteria_scores": {"Correctness": 7},
            "criterion_details": {"Correctness": {"applicable": True, "explanation": "Mostly correct", "evidence": "Lists are mutable", "evidence_supports_claim": True, "evidence_explanation": "This states the tested property."}},
            "technical_accuracy": "Mostly accurate",
            "missing_concepts": ["Mutation through references"],
            "correct_explanation": "A list can be changed in place.",
            "strengths": ["Identified mutability"], "weaknesses": ["No example"],
            "feedback": "Add a concrete example.", "needs_teacher_review": False,
        }
        with patch("queme.services.llm._generate", return_value=self._serialized_model_answer(answer)):
            with self.assertLogs("queme.services.llm", level="INFO") as captured:
                result = evaluate_answer({
                    "transcript": "Lists are mutable",
                    "rubric": {"criteria": [{"name": "Correctness", "weight": 100}]},
                }, correlation_id="answer_job:44")
        self.assertEqual(result["content_score"], 7.0)
        self.assertEqual(result["accuracy_category"], "MOSTLY_CORRECT_INCOMPLETE")
        self.assertEqual(result["missing_concepts"], ["Mutation through references"])
        self.assertEqual(result["correct_explanation"], "A list can be changed in place.")
        self.assertIn("Answer evaluation completed correlation_id=answer_job:44", "\n".join(captured.output))

    def test_evaluation_normalizes_qwen_singular_criterion_scores_key(self):
        answer = {
            "question_relevant": True, "relevance_explanation": "It answers the question.", "accuracy_category": "CORRECT_COMPLETE",
            "criterion_scores": {"Correctness": 8},
            "criterion_details": {"Correctness": {"applicable": True, "explanation": "Correct", "evidence": "Lists are mutable", "evidence_supports_claim": True, "evidence_explanation": "This directly supports the criterion."}},
            "technical_accuracy": "Correct.", "missing_concepts": [], "correct_explanation": "Lists can be changed.",
            "strengths": [], "weaknesses": [], "feedback": "Good.", "needs_teacher_review": False,
        }
        with patch("queme.services.llm._generate", return_value=self._serialized_model_answer(answer)):
            result = evaluate_answer({
                "transcript": "Lists are mutable",
                "rubric": {"criteria": [{"name": "Correctness", "weight": 100}]},
            })
        self.assertEqual(result["criteria_scores"], {"Correctness": 8.0})
        self.assertEqual(result["content_score"], 8.0)

    def test_followup_is_one_question_and_invalid_output_degrades_safely(self):
        with patch("queme.services.llm._generate", return_value='{"followup":"Can you explain why?"}'):
            self.assertEqual(generate_followup("Why?", "Because it works", "technical"), "Can you explain why?")
        with patch("queme.services.llm._generate", return_value="invalid"):
            self.assertIsNone(generate_followup("Why?", "Because it works", "technical"))

    def test_irrelevant_answer_keywords_cannot_keep_positive_scores(self):
        answer = {
            "question_relevant": False, "relevance_explanation": "It does not explain normalization.", "accuracy_category": "CORRECT_COMPLETE",
            "criteria_scores": {"Correctness": 9},
            "criterion_details": {"Correctness": {"applicable": True, "explanation": "Contains terms only.", "evidence": "SQL", "evidence_supports_claim": False, "evidence_explanation": "This only repeats a keyword."}},
            "technical_accuracy": "Correct", "missing_concepts": [], "correct_explanation": "Expected explanation.",
            "strengths": ["Excellent"], "weaknesses": [], "feedback": "Great answer.", "needs_teacher_review": False,
        }
        with patch("queme.services.llm._generate", return_value=self._serialized_model_answer(answer)):
            result = evaluate_answer({
                "question": "Explain database normalization", "transcript": "SQL is a language.",
                "rubric": {"criteria": [{"name": "Correctness", "weight": 100}]},
            })
        self.assertEqual(result["content_score"], 0.0)
        self.assertEqual(result["accuracy_category"], "INCORRECT_OR_IRRELEVANT")
        self.assertEqual(result["strengths"], [])
        self.assertIsNone(result["criterion_details"]["Correctness"]["evidence"])
        self.assertIn("No relevant technical claim", result["criterion_details"]["Correctness"]["explanation"])
        self.assertIn("does not address", result["feedback"])
        self.assertTrue(result["needs_teacher_review"])

    def test_missing_gemini_key_returns_review_without_fallback(self):
        self.app.config["EVALUATION_PROVIDER"] = "gemini"
        self.app.config["GEMINI_API_KEY"] = ""
        with patch("queme.services.llm._generate") as ollama:
            result = evaluate_answer({"question": "Q", "transcript": "A"})
        ollama.assert_not_called()
        self.assertIsNone(result["content_score"])
        self.assertTrue(result["needs_teacher_review"])
        self.assertNotIn("ollama", result["error"].lower())

    def test_gemini_timeout_failure_is_sanitized_for_teacher_review(self):
        self.app.config.update(EVALUATION_PROVIDER="gemini", GEMINI_API_KEY="secret-test-key")
        with patch("queme.services.llm._generate_gemini_json", side_effect=TimeoutError("quota secret-test-key")):
            result = evaluate_answer({"question": "Q", "transcript": "A"})
        self.assertTrue(result["needs_teacher_review"])
        self.assertIsNone(result["content_score"])
        self.assertNotIn("secret-test-key", result["error"])

    def test_contradictory_accuracy_label_is_reconciled_with_score(self):
        answer = {
            "question_relevant": True, "relevance_explanation": "It addresses the question.", "accuracy_category": "CORRECT_COMPLETE",
            "criteria_scores": {"Correctness": 5},
            "criterion_details": {"Correctness": {"applicable": True, "explanation": "Some detail.", "evidence": "A relevant statement.", "evidence_supports_claim": True, "evidence_explanation": "This statement supports the claim."}},
            "technical_accuracy": "Partially accurate", "missing_concepts": [], "correct_explanation": "Expected answer.",
            "strengths": ["One point"], "weaknesses": [], "feedback": "Continue.", "needs_teacher_review": False,
        }
        with patch("queme.services.llm._generate", return_value=self._serialized_model_answer(answer)):
            result = evaluate_answer({"transcript": "A relevant statement.", "rubric": {"criteria": [{"name": "Correctness", "weight": 100}]}})
        self.assertEqual(result["accuracy_category"], "PARTIALLY_CORRECT")
        self.assertTrue(result["needs_teacher_review"])

    def test_correct_answer_with_different_wording_has_supported_overall_evidence(self):
        answer = self._gemini_answer(
            evidence="Items can be inserted or removed later.",
        )
        answer["criterion_details"]["Overall"]["evidence_explanation"] = (
            "It describes adding and removing items after initialization."
        )
        with patch("queme.services.llm._generate", return_value=self._serialized_model_answer(answer)):
            result = evaluate_answer({
                "question": "Can a collection be modified after initialization?",
                "transcript": "Items can be inserted or removed later.",
            })
        self.assertEqual(result["content_score"], 8.0)
        self.assertEqual(result["criteria_scores"], {"Overall": 8.0})
        self.assertEqual(result["criterion_details"]["Overall"]["evidence"], "Items can be inserted or removed later.")
        self.assertTrue(result["needs_teacher_review"])
        self.assertEqual(result["review_reason"], "semantic_support_requires_teacher_review")

    def test_rubricless_score_without_evidence_is_insufficient(self):
        answer = self._gemini_answer(evidence=None)
        with patch("queme.services.llm._generate", return_value=json.dumps(answer)):
            result = evaluate_answer({"question": "Can a list change?", "transcript": "Yes."})
        self.assertIsNone(result["content_score"])
        self.assertEqual(result["accuracy_category"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result["criteria_scores"], {})
        self.assertTrue(result["needs_teacher_review"])

    def test_empty_transcript_never_calls_evaluator(self):
        with patch("queme.services.llm._generate") as generate:
            result = evaluate_answer({"question": "Explain lists", "transcript": ""})
        generate.assert_not_called()
        self.assertIsNone(result["content_score"])
        self.assertEqual(result["evaluation_status"], "UNAVAILABLE")

    def test_exact_but_unrelated_evidence_is_rejected(self):
        answer = self._gemini_answer(evidence="The sky is blue.", supports=False)
        with patch("queme.services.llm._generate", return_value=json.dumps(answer)):
            result = evaluate_answer({
                "question": "Can a list change after creation?",
                "transcript": "The sky is blue.",
            })
        self.assertIsNone(result["content_score"])
        self.assertEqual(result["accuracy_category"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result["criteria_scores"], {})

    def test_insufficient_evidence_clears_model_positive_feedback(self):
        answer = self._gemini_answer(evidence=None)
        with patch("queme.services.llm._generate", return_value=json.dumps(answer)):
            result = evaluate_answer({"question": "Explain mutability", "transcript": "Maybe."})
        self.assertEqual(result["strengths"], [])
        self.assertEqual(result["missing_concepts"], [])
        self.assertIn("could not be verified", result["correct_explanation"])
        self.assertIn("Insufficient evidence", result["technical_accuracy"])
        self.assertEqual(result["criterion_details"]["Overall"]["evidence"], None)
        self.assertEqual(result["criterion_details"]["Overall"]["explanation"], "Insufficient transcript evidence to evaluate this claim.")
        self.assertEqual(result["evaluation_status"], "UNAVAILABLE")

    def test_previous_qwen_rubricless_nested_scores_and_missing_explanation_are_rejected(self):
        malformed = {
            "criteria_scores": {"Overall": {"score": 8}},
            "criterion_details": {"Overall": {"applicable": True, "explanation": "Correct", "evidence": "Lists are mutable"}},
            "question_relevant": True, "relevance_explanation": "It mentions lists.",
            "accuracy_category": "CORRECT_COMPLETE", "technical_accuracy": "Correct",
            "missing_concepts": [], "strengths": [], "weaknesses": [],
            "feedback": "Good.", "needs_teacher_review": False,
        }
        with patch("queme.services.llm._generate", return_value=json.dumps(malformed)) as generate:
            result = evaluate_answer({"question": "Explain list mutability", "transcript": "Lists are mutable."})
        self.assertEqual(generate.call_count, 2)
        self.assertIsNone(result["content_score"])
        self.assertTrue(result["needs_teacher_review"])

    def test_dual_evaluation_is_sequential_independent_and_persists_each_result(self):
        self.app.config["EVALUATION_MODE"] = "dual_sequential"
        analysis = SimpleNamespace(
            transcript="The list can change after creation.", transcription_status="OK", delivery_score=8,
            to_dict=lambda: {name: None for name in (
                "answer_duration_seconds", "speaking_duration_seconds", "words_per_minute",
                "pause_count", "total_pause_duration_seconds", "longest_pause_seconds",
                "filler_word_count", "filler_word_rate", "repetition_count", "speech_ratio",
                "audio_quality_status",
            )},
        )
        question = SimpleNamespace(
            analysis=analysis, rubric=None,
            question=SimpleNamespace(question_text="Can a list change after creation?", question_type="technical", expected_key_points="", reference_answer=""),
            followup_text="", transcript=None, content_score=None, delivery_score=None, final_ai_score=None,
            needs_review=False, evaluation_json=None,
        )
        calls = []
        answer = self._gemini_answer()
        def provider(payload, *, correlation_id=None, provider_override=None):
            calls.append((provider_override, json.loads(json.dumps(payload))))
            return {**json.loads(json.dumps(answer)), "content_score": 8.0, "evaluation_status": "COMPLETED",
                    "provider_attempt": {"provider": provider_override, "model": "test-model", "status": "SUCCESS",
                                         "attempt_count": 1, "duration_ms": 10}}
        with patch("queme.services.reports.evaluate_answer", side_effect=provider), patch(
            "queme.services.reports.score_weights", return_value=(0.7, 0.3)
        ):
            result = evaluate_interview_answer(question, correlation_id="test")
        self.assertEqual([item[0] for item in calls], ["ollama", "gemini"])
        self.assertEqual(calls[0][1], calls[1][1])
        self.assertNotIn("dual_model", calls[1][1])
        self.assertEqual(result["dual_model"]["comparison"]["status"], "AGREEMENT")
        self.assertEqual(result["dual_model"]["providers"]["ollama"]["status"], "SUCCESS")
        self.assertEqual(result["dual_model"]["providers"]["gemini"]["status"], "SUCCESS")
        self.assertTrue(question.needs_review)  # Existing positive-score review safeguard remains.

    def test_dual_retry_reuses_successful_provider_and_comparison_threshold(self):
        self.app.config["EVALUATION_MODE"] = "dual_sequential"
        answer = {**self._gemini_answer(), "content_score": 8.0, "evaluation_status": "COMPLETED"}
        question = SimpleNamespace(
            analysis=SimpleNamespace(
                transcript="The list can change after creation.", transcription_status="OK", delivery_score=8,
                to_dict=lambda: {name: None for name in (
                    "answer_duration_seconds", "speaking_duration_seconds", "words_per_minute",
                    "pause_count", "total_pause_duration_seconds", "longest_pause_seconds",
                    "filler_word_count", "filler_word_rate", "repetition_count", "speech_ratio", "audio_quality_status",
                )},
            ), rubric=None,
            question=SimpleNamespace(question_text="Can a list change?", question_type="technical", expected_key_points="", reference_answer=""),
            followup_text="", transcript=None, content_score=None, delivery_score=None, final_ai_score=None,
            needs_review=False,
            evaluation_json={"dual_model": {"version": 1, "providers": {
                "ollama": {"status": "SUCCESS", "model": "qwen3:1.7b", "attempt_count": 1, "evaluation": answer},
                "gemini": {"status": "FAILED", "retryable": True, "attempt_count": 1, "error_category": "timeout"},
            }}},
        )
        with patch("queme.services.reports.evaluate_answer", return_value={
            **answer, "provider_attempt": {"provider": "gemini", "model": "gemini-test", "status": "SUCCESS", "attempt_count": 1, "duration_ms": 10}
        }) as provider, patch("queme.services.reports.score_weights", return_value=(0.7, 0.3)):
            result = evaluate_interview_answer(question)
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(provider.call_args.kwargs["provider_override"], "gemini")
        self.assertEqual(result["dual_model"]["comparison"]["status"], "AGREEMENT")
        comparison = _compare_dual_evaluations({
            "ollama": {"status": "SUCCESS", "evaluation": {**answer, "content_score": 7.0}},
            "gemini": {"status": "SUCCESS", "evaluation": {**answer, "content_score": 8.0}},
        })
        self.assertEqual(comparison["status"], "MINOR_DISAGREEMENT")
        self.assertEqual(comparison["score_difference"], 1.0)

    def test_dual_quota_failure_preserves_ollama_and_is_not_retried(self):
        self.app.config["EVALUATION_MODE"] = "dual_sequential"
        answer = {**self._gemini_answer(), "content_score": 8.0, "evaluation_status": "COMPLETED"}
        analysis = SimpleNamespace(
            transcript="The list can change after creation.", transcription_status="OK", delivery_score=8,
            to_dict=lambda: {name: None for name in (
                "answer_duration_seconds", "speaking_duration_seconds", "words_per_minute",
                "pause_count", "total_pause_duration_seconds", "longest_pause_seconds",
                "filler_word_count", "filler_word_rate", "repetition_count", "speech_ratio", "audio_quality_status",
            )},
        )
        question = SimpleNamespace(
            analysis=analysis, rubric=None,
            question=SimpleNamespace(question_text="Can a list change?", question_type="technical", expected_key_points="", reference_answer=""),
            followup_text="", transcript=None, content_score=None, delivery_score=None, final_ai_score=None,
            needs_review=False, evaluation_json=None,
        )
        ollama_success = {**answer, "provider_attempt": {
            "provider": "ollama", "model": "qwen3:1.7b", "status": "SUCCESS", "attempt_count": 1, "duration_ms": 1,
        }}
        gemini_quota_failure = {
            "content_score": None, "criteria_scores": {}, "needs_teacher_review": True,
            "error": "Evaluation provider failed; teacher review is required.",
            "error_category": "quota_exhausted", "retryable": False,
            "provider_attempt": {
                "provider": "gemini", "model": "gemini-3.5-flash-lite", "status": "FAILED",
                "attempt_count": 1, "duration_ms": 1, "error_category": "quota_exhausted", "retryable": False,
            },
        }
        with patch("queme.services.reports.evaluate_answer", side_effect=[ollama_success, gemini_quota_failure]) as provider, patch(
            "queme.services.reports.score_weights", return_value=(0.7, 0.3)
        ):
            result = evaluate_interview_answer(question)
            self.assertEqual([call.kwargs["provider_override"] for call in provider.call_args_list], ["ollama", "gemini"])
            self.assertEqual(result["dual_model"]["providers"]["ollama"]["status"], "SUCCESS")
            self.assertEqual(result["dual_model"]["providers"]["gemini"]["error_category"], "quota_exhausted")
            self.assertEqual(result["dual_model"]["comparison"]["status"], "INCOMPLETE")
            self.assertTrue(result["needs_teacher_review"])
            self.assertIsNone(result["content_score"])

            provider.reset_mock()
            retried = evaluate_interview_answer(question)
        provider.assert_not_called()
        self.assertEqual(retried["dual_model"]["providers"]["ollama"]["status"], "SUCCESS")
        self.assertEqual(retried["dual_model"]["providers"]["gemini"]["status"], "FAILED")

    def test_dual_comparison_threshold_relevance_and_incomplete_rules(self):
        baseline = {**self._gemini_answer(), "content_score": 7.0, "evaluation_status": "COMPLETED"}
        def compare(score, *, gemini_relevant=True, gemini_status="SUCCESS"):
            gemini_eval = {**baseline, "content_score": score, "question_relevant": gemini_relevant}
            return _compare_dual_evaluations({
                "ollama": {"status": "SUCCESS", "evaluation": baseline},
                "gemini": {"status": gemini_status, "evaluation": gemini_eval},
            })
        self.assertEqual(compare(8.99)["status"], "MINOR_DISAGREEMENT")
        self.assertEqual(compare(9.0)["status"], "MATERIAL_DISAGREEMENT")
        self.assertEqual(compare(9.01)["status"], "MATERIAL_DISAGREEMENT")
        self.assertIn("relevance_disagreement", compare(7.0, gemini_relevant=False)["teacher_review_reasons"])
        self.assertEqual(compare(7.0, gemini_status="FAILED")["status"], "INCOMPLETE")

    def test_provider_error_categories_are_sanitized_and_distinct(self):
        self.assertEqual(_provider_error_category(TimeoutError("private transcript")), "timeout")
        self.assertEqual(_provider_error_category(self._google_api_error(403, "Permission denied")), "authentication")
        quota_failure = {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"subject": "project quota"}]}
        structured_quota = self._google_api_error(429, "You exceeded your current quota.", [quota_failure])
        self.assertEqual(_provider_error_category(structured_quota), "quota_exhausted")
        self.assertFalse(_failure_is_retryable(_provider_error_category(structured_quota)))
        structured_reason = self._google_api_error(429, "Request rejected.", [{
            "@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "PROJECT_QUOTA_EXCEEDED",
        }])
        self.assertEqual(_provider_error_category(structured_reason), "quota_exhausted")
        for message in (
            "You exceeded your daily quota for this project.",
            "You exceeded your current project quota.",
        ):
            with self.subTest(message=message):
                category = _provider_error_category(self._google_api_error(429, message))
                self.assertEqual(category, "quota_exhausted")
                self.assertFalse(_failure_is_retryable(category))
        temporary = self._google_api_error(429, "Rate limit exceeded: requests per minute; retry after 1s.")
        self.assertEqual(_provider_error_category(temporary), "rate_limit")
        self.assertTrue(_failure_is_retryable(_provider_error_category(temporary)))
        temporary_reason = self._google_api_error(429, "Request rejected.", [{
            "@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "RATE_LIMIT_EXCEEDED",
        }])
        self.assertEqual(_provider_error_category(temporary_reason), "rate_limit")
        unknown = self._google_api_error(429, "Unexpected provider response")
        self.assertEqual(_provider_error_category(unknown), "unknown_rate_limit")
        self.assertFalse(_failure_is_retryable(_provider_error_category(unknown)))
        self.assertEqual(_provider_error_category(URLError("network endpoint")), "network")
        self.assertEqual(_provider_error_category(ValueError("Gemini returned invalid JSON.")), "invalid_json")

    def test_gemini_quota_error_is_sanitized_for_teacher_review(self):
        self.app.config.update(EVALUATION_PROVIDER="gemini", GEMINI_API_KEY="test-key")
        quota_error = self._google_api_error(429, "You exceeded your current quota; private detail.", [{
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [{"subject": "private project detail"}],
        }])
        with patch("queme.services.llm._generate_gemini_json", side_effect=quota_error):
            result = evaluate_answer({"question": "Q", "transcript": "synthetic private transcript"})
        self.assertEqual(result["error_category"], "quota_exhausted")
        self.assertFalse(result["retryable"])
        self.assertTrue(result["needs_teacher_review"])
        self.assertIsNone(result["content_score"])
        self.assertNotIn("private", result["error"])
        self.assertNotIn("synthetic", result["error"])

    def test_high_delivery_does_not_increase_incorrect_content_score(self):
        analysis = SimpleNamespace(
            transcript="I am confident, but the answer is wrong.",
            transcription_status="OK", delivery_score=10,
            to_dict=lambda: {name: None for name in (
                "answer_duration_seconds", "speaking_duration_seconds", "words_per_minute",
                "pause_count", "total_pause_duration_seconds", "longest_pause_seconds",
                "filler_word_count", "filler_word_rate", "repetition_count", "speech_ratio",
                "audio_quality_status",
            )},
        )
        question = SimpleNamespace(
            analysis=analysis,
            rubric=None,
            question=SimpleNamespace(question_text="Explain binary search", question_type="technical", expected_key_points="", reference_answer=""),
            followup_text="", transcript=None, content_score=None, delivery_score=None, final_ai_score=None,
            needs_review=False, evaluation_json=None,
        )
        evaluation = {
            "content_score": 0.0, "accuracy_category": "INCORRECT_OR_IRRELEVANT",
            "needs_teacher_review": False, "criteria_scores": {},
        }
        with patch("queme.services.reports.evaluate_answer", return_value=evaluation), patch(
            "queme.services.reports.score_weights", return_value=(0.7, 0.3)
        ):
            evaluate_interview_answer(question)
        self.assertEqual(question.content_score, 0.0)
        self.assertEqual(question.delivery_score, 10)
        self.assertEqual(question.final_ai_score, 0.0)

    def test_gemini_sdk_request_schema_timeout_and_valid_result(self):
        answer = self._gemini_answer()
        modules, client, genai_module, types_module = self._mock_google_sdk(json.dumps(answer))
        self.app.config.update(EVALUATION_PROVIDER="gemini", GEMINI_API_KEY="test-key")
        with patch.dict(sys.modules, modules):
            result = evaluate_answer({
                "question": "Can a list change after creation?",
                "transcript": "The list can change after creation.",
            })
        self.assertEqual(result["content_score"], 8.0)
        genai_module.Client.assert_called_once()
        self.assertEqual(genai_module.Client.call_args.kwargs["api_key"], "test-key")
        self.assertEqual(types_module.HttpOptions.call_args.kwargs["timeout"], 30000)
        self.assertEqual(types_module.HttpRetryOptions.call_args.kwargs["attempts"], 1)
        request = client.models.generate_content.call_args.kwargs
        self.assertEqual(request["model"], "gemini-3.5-flash-lite")
        self.assertEqual(request["config"]["response_mime_type"], "application/json")
        self.assertIn("evidence_supports_claim", request["config"]["response_schema"]["properties"]["criterion_details"]["properties"]["Overall"]["properties"])

    def test_gemini_invalid_response_is_rejected_without_ollama_fallback(self):
        modules, client, _, _ = self._mock_google_sdk("{bad json")
        self.app.config.update(EVALUATION_PROVIDER="gemini", GEMINI_API_KEY="test-key")
        with patch.dict(sys.modules, modules), patch("queme.services.llm._generate") as ollama:
            result = evaluate_answer({"question": "Q", "transcript": "A"})
        ollama.assert_not_called()
        self.assertEqual(client.models.generate_content.call_count, 1)
        self.assertIsNone(result["content_score"])
        self.assertTrue(result["needs_teacher_review"])

    def test_gemini_sdk_timeout_and_temporary_rate_limit_retry_only_once(self):
        for failure in (
            TimeoutError("timeout"),
            self._google_api_error(429, "Rate limit exceeded: requests per minute; retry after 1s."),
        ):
            with self.subTest(failure=type(failure).__name__):
                modules, client, _, types_module = self._mock_google_sdk(side_effect=[failure, failure])
                self.app.config.update(EVALUATION_PROVIDER="gemini", GEMINI_API_KEY="test-key")
                with patch.dict(sys.modules, modules), patch("queme.services.llm.time.sleep") as sleep, patch(
                    "queme.services.llm._generate"
                ) as ollama:
                    result = evaluate_answer({"question": "Q", "transcript": "A"})
                self.assertEqual(types_module.HttpOptions.call_args.kwargs["timeout"], 30000)
                self.assertEqual(client.models.generate_content.call_count, 2)
                sleep.assert_called_once_with(1)
                ollama.assert_not_called()
                self.assertTrue(result["needs_teacher_review"])
                self.assertIsNone(result["content_score"])


if __name__ == "__main__":
    unittest.main()
