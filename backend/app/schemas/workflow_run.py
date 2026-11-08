from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import WorkflowRunStatus


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class WorkflowRunResponse(BaseModel):
    id: uuid.UUID
    complaint_id: uuid.UUID
    status: WorkflowRunStatus
    current_step: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    error_message: str | None = None


class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunResponse]
    total: int
    limit: int
    offset: int


class WorkflowRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_step: str | None = Field(default=None, max_length=100)

    @field_validator("current_step")
    @classmethod
    def normalize_current_step(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class WorkflowRunStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: WorkflowRunStatus
    current_step: str | None = Field(default=None, max_length=100)
    error_message: str | None = Field(default=None, max_length=2000)

    @field_validator("current_step", "error_message")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def restrict_error_message_to_failures(self) -> WorkflowRunStatusUpdate:
        if (
            self.error_message is not None
            and self.status is not WorkflowRunStatus.FAILED
        ):
            raise ValueError(
                "error_message is only permitted when status is failed"
            )
        return self
