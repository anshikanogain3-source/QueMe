import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from flask import g, jsonify
from sqlalchemy.exc import IntegrityError

from queme import create_app
from queme.logging_config import WerkzeugAccessFilter, configure_logging


class ApplicationLoggingTests(unittest.TestCase):
    def setUp(self):
        self.log_dir = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "PROPAGATE_EXCEPTIONS": False,
            "SECRET_KEY": "test-secret-key-that-is-long-enough-for-tests",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "STORAGE_BACKEND": "local",
            "STORAGE_LOCAL_DIR": Path(self.log_dir.name) / "uploads",
            "JWT_EXP_HOURS": 24,
            "FRONTEND_ORIGIN": "http://localhost:5173",
            "LOG_LEVEL": "DEBUG",
            "LOG_DIR": self.log_dir.name,
            "LOG_MAX_BYTES": 1024,
            "LOG_BACKUP_COUNT": 2,
        })

        @self.app.get("/api/test-access")
        def test_access():
            g.user = SimpleNamespace(role="teacher", user_id=123)
            return jsonify({"ok": True})

        @self.app.get("/api/test-failure")
        def test_failure():
            raise RuntimeError("Failure for student@example.test token=private-value")

        @self.app.get("/api/test-db-error")
        def test_database_error():
            raise IntegrityError("INSERT INTO users", {"email": "student@example.test"}, Exception("duplicate"))

        self.client = self.app.test_client()

    def tearDown(self):
        self.log_dir.cleanup()

    def test_api_access_record_uses_safe_endpoint_and_request_id(self):
        response = self.client.get(
            "/api/test-access?token=query-secret",
            headers={"Authorization": "Bearer header-secret"},
        )
        request_id = response.headers.get("X-Request-ID")
        access_log = (Path(self.log_dir.name) / "access.log").read_text()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(request_id)
        self.assertIn(f"request_id={request_id}", access_log)
        self.assertIn("method=GET endpoint=test_access status=200", access_log)
        self.assertIn("role=teacher", access_log)
        self.assertNotIn("query-secret", access_log)
        self.assertNotIn("header-secret", access_log)
        self.assertNotIn("user_id=123", access_log)

    def test_unexpected_exception_has_traceback_and_redacts_sensitive_values(self):
        response = self.client.get("/api/test-failure")
        error_log = (Path(self.log_dir.name) / "errors.log").read_text()
        general_log = (Path(self.log_dir.name) / "queme.log").read_text()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {"error": "An unexpected server error occurred.", "code": "internal_error"})
        self.assertIn("Traceback (most recent call last)", error_log)
        self.assertIn("RuntimeError", error_log)
        self.assertIn("[REDACTED_EMAIL]", error_log)
        self.assertIn("token=[REDACTED]", error_log)
        self.assertNotIn("student@example.test", general_log)
        self.assertNotIn("private-value", general_log)
        access_log = (Path(self.log_dir.name) / "access.log").read_text()
        self.assertIn("endpoint=test_failure status=500", access_log)

    def test_handled_database_conflict_is_logged_without_sql_values(self):
        response = self.client.get("/api/test-db-error")
        error_log = (Path(self.log_dir.name) / "errors.log").read_text()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "data_conflict")
        self.assertIn("Database integrity conflict handled error_type=IntegrityError", error_log)
        self.assertNotIn("student@example.test", error_log)

    def test_logging_setup_is_idempotent_and_writes_to_console_and_files(self):
        configure_logging(self.app)
        configure_logging(self.app)
        managed_root_handlers = [
            handler for handler in logging.getLogger().handlers
            if getattr(handler, "_queme_logging_handler", False)
        ]
        managed_access_handlers = [
            handler for handler in logging.getLogger("queme.access").handlers
            if getattr(handler, "_queme_logging_handler", False)
        ]
        self.assertEqual(len(managed_root_handlers), 3)
        self.assertEqual(sum(type(handler) is logging.StreamHandler for handler in managed_root_handlers), 1)
        self.assertEqual(len(managed_access_handlers), 2)

        logging.getLogger("queme").debug("debug file output")
        logging.getLogger("queme").info(
            "metric prompt_tokens=%s auth_token=%s smtp_password=%s service_url=%s",
            42,
            "test-token",
            "smtp-secret",
            "https://user:password@service.test",
        )
        self.client.get("/api/test-access")
        general_log = (Path(self.log_dir.name) / "queme.log").read_text()
        access_log = (Path(self.log_dir.name) / "access.log").read_text().splitlines()
        self.assertIn("debug file output", general_log)
        self.assertIn("prompt_tokens=42", general_log)
        self.assertIn("auth_token=[REDACTED]", general_log)
        self.assertNotIn("smtp-secret", general_log)
        self.assertNotIn("user:password", general_log)
        self.assertEqual(sum("endpoint=test_access" in line for line in access_log), 1)

        logger = logging.getLogger("queme")
        for index in range(8):
            logger.info("rotation check %d %s", index, "x" * 400)
        self.assertTrue((Path(self.log_dir.name) / "queme.log.1").exists())
        self.assertTrue((Path(self.log_dir.name) / "queme.log.2").exists())
        self.assertFalse((Path(self.log_dir.name) / "queme.log.3").exists())

    def test_werkzeug_access_lines_are_suppressed_but_startup_messages_remain(self):
        access_record = logging.LogRecord(
            "werkzeug", logging.INFO, "", 0,
            '%s - - [%s] "%s %s %s" %s -',
            ("127.0.0.1", "12/Nov/2026 12:00:00", "GET", "/api/health", "HTTP/1.1", 200),
            None,
        )
        startup_record = logging.LogRecord(
            "werkzeug", logging.INFO, "", 0, " * Running on http://127.0.0.1:5000", (), None
        )
        access_filter = WerkzeugAccessFilter()

        self.assertFalse(access_filter.filter(access_record))
        self.assertTrue(access_filter.filter(startup_record))


if __name__ == "__main__":
    unittest.main()
