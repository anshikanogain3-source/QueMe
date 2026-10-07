"""Server-side authorization tests for the administrator management API.

Hidden navigation items are never authorization: every /admin route must
reject unauthenticated callers with 401 and non-admin principals with 403."""
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.auth import Principal, require_admin
from backend.app.main import app
from backend.app.schemas import CoordinatorAssignmentCreate, InterviewAssignmentCreate

ADMIN_ROUTES = [
    ("GET", "/api/v1/admin/accounts"),
    ("GET", "/api/v1/admin/departments"),
    ("GET", "/api/v1/admin/courses"),
    ("GET", "/api/v1/admin/semesters"),
    ("GET", "/api/v1/admin/batches"),
    ("GET", "/api/v1/admin/classes"),
    ("GET", "/api/v1/admin/enrollments"),
    ("GET", "/api/v1/admin/teacher-assignments"),
    ("GET", "/api/v1/admin/coordinator-assignments"),
    ("GET", "/api/v1/admin/interview-assignments"),
    ("GET", "/api/v1/admin/audit-events"),
    ("POST", "/api/v1/admin/invitations"),
    ("POST", "/api/v1/admin/enrollments"),
    ("POST", "/api/v1/admin/teacher-assignments"),
    ("POST", "/api/v1/admin/coordinator-assignments"),
    ("POST", "/api/v1/admin/interview-assignments"),
    ("POST", "/api/v1/admin/accounts/11111111-1111-1111-1111-111111111111/activate"),
    ("POST", "/api/v1/admin/accounts/11111111-1111-1111-1111-111111111111/deactivate"),
    ("DELETE", "/api/v1/admin/accounts/11111111-1111-1111-1111-111111111111"),
    ("DELETE", "/api/v1/admin/enrollments/11111111-1111-1111-1111-111111111111"),
    ("PATCH", "/api/v1/admin/courses/11111111-1111-1111-1111-111111111111"),
    ("DELETE", "/api/v1/admin/courses/11111111-1111-1111-1111-111111111111"),
]


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_routes_require_authentication(method: str, path: str) -> None:
    with TestClient(app) as client:
        response = client.request(method, path)
    assert response.status_code == 401, f"{method} {path} returned {response.status_code}"
    assert response.json()["error"]["code"] == "unauthorized"


def _principal(role: str) -> Principal:
    return Principal(user_id=str(uuid.uuid4()), email=f"{role}@example.com", access_token="token", role=role)


def test_require_admin_rejects_non_admin_roles() -> None:
    for role in ("student", "teacher", "coordinator"):
        with pytest.raises(HTTPException) as exc:
            require_admin(_principal(role))
        assert exc.value.status_code == 403


def test_require_admin_allows_admin() -> None:
    assert require_admin(_principal("admin")).role == "admin"


def test_coordinator_scope_requires_matching_reference() -> None:
    coordinator = uuid.uuid4()
    with pytest.raises(ValidationError):
        CoordinatorAssignmentCreate(coordinator_id=coordinator, scope_type="class")  # missing class_id
    with pytest.raises(ValidationError):
        CoordinatorAssignmentCreate(
            coordinator_id=coordinator, scope_type="class", class_id=uuid.uuid4(), course_id=uuid.uuid4()
        )
    ok = CoordinatorAssignmentCreate(coordinator_id=coordinator, scope_type="class", class_id=uuid.uuid4())
    assert ok.scope_type == "class"


def test_interview_assignment_configuration_bounds() -> None:
    base = dict(
        student_id=uuid.uuid4(), class_id=uuid.uuid4(),
        interview_type="Technical", target_role="Backend Engineer",
    )
    assert InterviewAssignmentCreate(**base).question_target_count == 5
    with pytest.raises(ValidationError):
        InterviewAssignmentCreate(**{**base, "question_target_count": 0})
    with pytest.raises(ValidationError):
        InterviewAssignmentCreate(**{**base, "question_target_count": 31})
    with pytest.raises(ValidationError):
        InterviewAssignmentCreate(**{**base, "difficulty": "impossible"})