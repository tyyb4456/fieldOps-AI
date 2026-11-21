from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import (
    ComplaintChannel,
    ComplaintStatus,
    Priority,
)


class ComplaintResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    equipment_id: uuid.UUID | None = None
    description: str
    reported_symptoms: list[Any]
    reported_error_code: str | None = None
    channel: ComplaintChannel
    status: ComplaintStatus
    priority: Priority
    created_at: datetime
    updated_at: datetime


class ComplaintListResponse(BaseModel):
    items: list[ComplaintResponse]
    total: int
    limit: int
    offset: int


class ComplaintHistoryResponse(BaseModel):
    id: uuid.UUID
    complaint_id: uuid.UUID
    sequence_number: int
    event_type: str
    from_status: ComplaintStatus | None = None
    to_status: ComplaintStatus | None = None
    changed_fields: dict[str, Any]
    actor_id: uuid.UUID | None = None
    created_at: datetime


class ComplaintHistoryListResponse(BaseModel):
    items: list[ComplaintHistoryResponse]
    total: int


class ComplaintStatusTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ComplaintStatus
    expected_status: ComplaintStatus
    reason: str | None = Field(default=None, max_length=4000)
    reason_code: str | None = Field(default=None, max_length=100)
    diagnostic_workflow_run_id: uuid.UUID | None = None
    resolution_code: str | None = Field(default=None, max_length=100)
    resolution_summary: str | None = Field(default=None, max_length=4000)

    @field_validator(
        "reason",
        "reason_code",
        "resolution_code",
        "resolution_summary",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def validate_transition_request(self) -> ComplaintStatusTransitionRequest:
        if self.status is self.expected_status:
            raise ValueError("status must differ from expected_status")
        if self.status in (
            ComplaintStatus.RECEIVED,
            ComplaintStatus.CONVERTED,
        ):
            raise ValueError(f"{self.status.value} cannot be a target status")
        if self.status in (
            ComplaintStatus.AWAITING_CUSTOMER,
            ComplaintStatus.ESCALATED,
        ) and not self.reason:
            raise ValueError(f"{self.status.value} requires a reason")
        if self.status is ComplaintStatus.CLOSED and (
            not self.resolution_code or not self.resolution_summary
        ):
            raise ValueError(
                "closed requires resolution_code and resolution_summary"
            )
        return self


class ComplaintStatusTransitionResponse(BaseModel):
    complaint: ComplaintResponse
    history: ComplaintHistoryResponse
    available_transitions: list[ComplaintStatus]


class ComplaintCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=5, max_length=10000)
    equipment_id: uuid.UUID | None = None
    reported_error_code: str | None = Field(default=None, max_length=100)
    channel: ComplaintChannel = ComplaintChannel.WEB

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 5:
            raise ValueError("description must be at least 5 characters")
        return stripped

    @field_validator("reported_error_code")
    @classmethod
    def normalize_error_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ComplaintUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(
        default=None,
        min_length=5,
        max_length=10000,
    )
    reported_error_code: str | None = Field(default=None, max_length=100)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("description may not be null")
        stripped = value.strip()
        if len(stripped) < 5:
            raise ValueError("description must be at least 5 characters")
        return stripped

    @field_validator("reported_error_code")
    @classmethod
    def normalize_error_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> ComplaintUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self
