from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator



class AudioJobSubmission(BaseModel):
    session_id: UUID
    storage_object_path: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")

    @field_validator("storage_object_path")
    @classmethod
    def validate_storage_path(cls, value: str) -> str:
        if value.startswith(("/", "http://", "https://")) or ".." in value.split("/"):
            raise ValueError("Must be a private storage object path, not a URL or traversal path.")
        return value


class AudioJobAccepted(BaseModel):
    id: UUID
    status: str
    attempt_count: int
    max_attempts: int
    request_id: str


class CreateManagedUser(BaseModel):
    email: str
    full_name: str = Field(min_length=1, max_length=200)
    role: str = Field(pattern=r"^(student|teacher|coordinator|admin)$")


class ManagedUser(BaseModel):
    id: UUID
    email: str
    role: str


# ------------------------------------------------------------------
# Administrator management API
# ------------------------------------------------------------------

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
CODE_PATTERN = r"^[A-Za-z0-9._-]+$"


class PageResult(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int


class InviteAccount(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    full_name: str = Field(min_length=1, max_length=200)
    role: str = Field(pattern=r"^(student|teacher|coordinator)$")


class DepartmentCreate(BaseModel):
    code: str = Field(min_length=2, max_length=20, pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=120)


class CourseCreate(BaseModel):
    department_id: UUID
    code: str = Field(min_length=2, max_length=20, pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    program_level: str = Field(min_length=1, max_length=40)
    duration_semesters: int = Field(default=6, ge=1, le=12)
    is_active: bool = True


class CourseUpdate(BaseModel):
    department_id: UUID | None = None
    code: str | None = Field(default=None, min_length=2, max_length=20, pattern=CODE_PATTERN)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    program_level: str | None = Field(default=None, min_length=1, max_length=40)
    duration_semesters: int | None = Field(default=None, ge=1, le=12)
    is_active: bool | None = None


class SemesterCreate(BaseModel):
    course_id: UUID
    number: int = Field(ge=1, le=12)
    label: str = Field(min_length=1, max_length=60)


class SemesterUpdate(BaseModel):
    course_id: UUID | None = None
    number: int | None = Field(default=None, ge=1, le=12)
    label: str | None = Field(default=None, min_length=1, max_length=60)


class BatchCreate(BaseModel):
    course_id: UUID
    start_year: int = Field(ge=2000, le=2100)
    label: str = Field(min_length=1, max_length=60)


class BatchUpdate(BaseModel):
    course_id: UUID | None = None
    start_year: int | None = Field(default=None, ge=2000, le=2100)
    label: str | None = Field(default=None, min_length=1, max_length=60)


class ClassCreate(BaseModel):
    course_id: UUID
    semester_id: UUID
    batch_id: UUID
    section: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=80)


class ClassUpdate(BaseModel):
    course_id: UUID | None = None
    semester_id: UUID | None = None
    batch_id: UUID | None = None
    section: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=80)


class EnrollmentCreate(BaseModel):
    student_id: UUID
    class_id: UUID
    status: str = Field(default="active", pattern=r"^(active|inactive|completed)$")
    notes: str | None = Field(default=None, max_length=500)


class TeacherAssignmentCreate(BaseModel):
    teacher_id: UUID
    class_id: UUID


class CoordinatorAssignmentCreate(BaseModel):
    coordinator_id: UUID
    scope_type: str = Field(pattern=r"^(class|semester|course|department)$")
    class_id: UUID | None = None
    semester_id: UUID | None = None
    course_id: UUID | None = None
    department_id: UUID | None = None

    @model_validator(mode="after")
    def _scope_matches_reference(self) -> "CoordinatorAssignmentCreate":
        supplied = {
            "class": self.class_id,
            "semester": self.semester_id,
            "course": self.course_id,
            "department": self.department_id,
        }
        if supplied[self.scope_type] is None:
            raise ValueError(f"{self.scope_type}_id is required for scope_type '{self.scope_type}'")
        for name, value in supplied.items():
            if name != self.scope_type and value is not None:
                raise ValueError(f"{name}_id must not be set when scope_type is '{self.scope_type}'")
        return self


class InterviewAssignmentCreate(BaseModel):
    student_id: UUID
    class_id: UUID
    interview_type: str = Field(min_length=1, max_length=80)
    target_role: str = Field(min_length=1, max_length=80)
    experience_level: str = Field(default="beginner", pattern=r"^(beginner|intermediate|advanced)$")
    difficulty: str = Field(default="adaptive", pattern=r"^(easy|medium|hard|adaptive)$")
    question_target_count: int = Field(default=5, ge=1, le=30)
    due_at: datetime | None = None


class InterviewAssignmentUpdate(BaseModel):
    interview_type: str | None = Field(default=None, min_length=1, max_length=80)
    target_role: str | None = Field(default=None, min_length=1, max_length=80)
    experience_level: str | None = Field(default=None, pattern=r"^(beginner|intermediate|advanced)$")
    difficulty: str | None = Field(default=None, pattern=r"^(easy|medium|hard|adaptive)$")
    question_target_count: int | None = Field(default=None, ge=1, le=30)
    due_at: datetime | None = None
    status: str | None = Field(default=None, pattern=r"^(assigned|in_progress|completed|cancelled)$")
