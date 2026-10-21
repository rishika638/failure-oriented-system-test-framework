from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CaptureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: Literal["latency", "timeout", "dependency"]
    method: Literal["GET"]
    path: str = Field(min_length=1, max_length=512, pattern=r"^/[A-Za-z0-9._~/-]*$")
    status_code: int = Field(ge=100, le=599)
    latency_ms: float = Field(ge=0, le=300_000, allow_inf_nan=False)
    request_id: str = Field(min_length=1, max_length=128)
    headers: dict[str, str] = Field(default_factory=dict, max_length=50)
    body: dict[str, Any] | None = None
    occurred_at: datetime

    @field_validator("path")
    @classmethod
    def reject_traversal(cls, value):
        if "//" in value or any(part in {".", ".."} for part in value.split("/")):
            raise ValueError("path must not contain traversal segments")
        return value

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value


class FailureSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    capture_id: UUID
    scenario: Literal["latency", "timeout", "dependency"]
    captured_at: datetime
    request: dict[str, Any]
    measurements: dict[str, Any]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
