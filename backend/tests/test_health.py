from fastapi.testclient import TestClient

from backend.app.config import get_settings
from backend.app.main import app


def test_health_returns_request_id() -> None:
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "not-a-uuid"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert response.headers["x-request-id"] != "not-a-uuid"


def test_validation_error_uses_shared_envelope() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/audio-jobs", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["request_id"] == response.headers["x-request-id"]
    assert body["error"]["details"]


def test_readiness_reports_database_configuration_gap(monkeypatch) -> None:
    monkeypatch.delenv("QUEME_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.get("/ready")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_not_configured"
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_audio_job_submission_is_disabled_without_server_token() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/audio-jobs",
            json={
                "session_id": "748f6c1f-0c21-4c4d-9452-72ce0f14c78e",
                "storage_object_path": "private/session/recording.webm",
                "idempotency_key": "test-job-key-001",
            },
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_not_configured"


def test_audio_job_submission_rejects_invalid_internal_token(monkeypatch) -> None:
    monkeypatch.setenv("QUEME_INTERNAL_API_TOKEN", "server-only-test-token")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/audio-jobs",
                headers={"X-Internal-Token": "wrong-token"},
                json={
                    "session_id": "748f6c1f-0c21-4c4d-9452-72ce0f14c78e",
                    "storage_object_path": "private/session/recording.webm",
                    "idempotency_key": "test-job-key-002",
                },
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
