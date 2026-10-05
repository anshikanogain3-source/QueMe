from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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
