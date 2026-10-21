from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    name: Literal["latency", "timeout", "dependency"]
    method: Literal["GET"]
    path: str = Field(pattern=r"^/[A-Za-z0-9._~/-]*$", max_length=512)
    fault: Literal["latency", "timeout", "dependency"]
    latency_ms: int = Field(default=0, ge=0, le=10_000)
    timeout_ms: int = Field(default=1000, ge=1, le=30_000)
    expected_status: int = Field(default=200, ge=100, le=599)
    recovery_max_latency_ms: int = Field(default=500, ge=1, le=30_000)

    @field_validator("path")
    @classmethod
    def safe_path(cls, value):
        if "//" in value or any(part in {".", ".."} for part in value.split("/")):
            raise ValueError("path must not contain traversal segments")
        return value
