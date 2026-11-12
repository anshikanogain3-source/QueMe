import io
import json
import socket
import unittest
from urllib.error import URLError
from unittest.mock import patch

from queme import create_app
from queme.services.llm import _check_model_available, _generate, _generate_json, evaluate_answer, generate_followup, generate_questions


class LocalOllamaTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret-key-that-is-long-enough-for-tests",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "STORAGE_BACKEND": "local",
            "JWT_EXP_HOURS": 24,
            "FRONTEND_ORIGIN": "http://localhost:5173",
            "OLLAMA_BASE_URL": "http://localhost:11434",
            "OLLAMA_MODEL": "qwen3.5:4b",
            "OLLAMA_KEEP_ALIVE": "30m",
            "OLLAMA_TIMEOUT": 120,
            "OLLAMA_TEMPERATURE": 0.2,
            "OLLAMA_NUM_CTX": 4096,
        })
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_chat_request_uses_local_endpoint_and_configured_controls(self):
        response = io.BytesIO(json.dumps({"message": {"content": "{\"ok\":true}"}, "prompt_eval_count": 20, "eval_count": 4}).encode())
        response.__enter__ = lambda: response
        response.__exit__ = lambda *_args: None
        with patch("queme.services.llm.urlopen", return_value=response) as urlopen:
            self.assertEqual(_generate("return JSON", num_predict=55), '{"ok":true}')
        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "http://localhost:11434/api/chat")
        self.assertEqual(body["model"], "qwen3.5:4b")
        self.assertFalse(body["think"])
        self.assertEqual(body["keep_alive"], "30m")
        self.assertEqual(body["options"], {"temperature": 0.2, "num_predict": 55, "num_ctx": 4096})
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 120)

    def test_model_check_uses_tags_and_requires_the_configured_model(self):
        response = io.BytesIO(json.dumps({"models": [{"name": "qwen3.5:4b"}]}).encode())
        with patch("queme.services.llm.urlopen", return_value=response) as urlopen:
            _check_model_available()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:11434/api/tags")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)

        response = io.BytesIO(json.dumps({"models": [{"name": "other-model:latest"}]}).encode())
        with patch("queme.services.llm.urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "qwen3.5:4b.*not installed"):
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
            result = _generate_json("prompt", validator=lambda value: isinstance(value, dict))
        self.assertEqual(result, {"followup": None})
        self.assertEqual(generate.call_count, 2)

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
            "criteria_scores": {"Correctness": 7},
            "criterion_details": {"Correctness": {"applicable": True, "explanation": "Mostly correct", "evidence": "Lists are mutable"}},
            "technical_accuracy": "Mostly accurate",
            "missing_concepts": ["Mutation through references"],
            "correct_explanation": "A list can be changed in place.",
            "strengths": ["Identified mutability"], "weaknesses": ["No example"],
            "feedback": "Add a concrete example.", "needs_teacher_review": False,
        }
        with patch("queme.services.llm._generate", return_value=json.dumps(answer)):
            result = evaluate_answer({
                "transcript": "Lists are mutable",
                "rubric": {"criteria": [{"name": "Correctness", "weight": 100}]},
            })
        self.assertEqual(result["content_score"], 7.0)
        self.assertEqual(result["missing_concepts"], ["Mutation through references"])
        self.assertEqual(result["correct_explanation"], "A list can be changed in place.")

    def test_evaluation_normalizes_qwen_singular_criterion_scores_key(self):
        answer = {
            "criterion_scores": {"Correctness": 8},
            "criterion_details": {"Correctness": {"applicable": True, "explanation": "Correct", "evidence": "Lists are mutable"}},
            "strengths": [], "weaknesses": [], "feedback": "Good.", "needs_teacher_review": False,
        }
        with patch("queme.services.llm._generate", return_value=json.dumps(answer)):
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


if __name__ == "__main__":
    unittest.main()
