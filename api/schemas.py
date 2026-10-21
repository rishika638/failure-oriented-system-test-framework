from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capture_id: UUID


class IncidentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "investigating", "resolved"]
