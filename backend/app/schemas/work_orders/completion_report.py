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

from app.models.enums import EvidenceStatus


def _normalize_required_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Field must not be blank")
    return stripped


class CompletionReportResponse(BaseModel):
    id: uuid.UUID
    work_order_id: uuid.UUID
    service_record_id: uuid.UUID | None = None
    summary: str
    evidence_status: EvidenceStatus
    verification_notes: str | None = None
    submitted_at: datetime
    verified_at: datetime | None = None


class CompletionReportListResponse(BaseModel):
    items: list[CompletionReportResponse]
    total: int
    limit: int
    offset: int


class CompletionReportCreate(BaseModel):
    """Submit completion evidence for a work order.

    ``work_order_id`` comes from the URL. The technician, evidence status and
    timestamps are server-controlled and intentionally rejected if supplied
    by the client.
    """

    model_config = ConfigDict(extra="forbid")

    service_record_id: uuid.UUID
    summary: str = Field(min_length=1, max_length=10000)

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        return _normalize_required_text(value)


class CompletionReportUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str | None = Field(default=None, min_length=1, max_length=10000)
    evidence_status: EvidenceStatus | None = None
    verification_notes: str | None = Field(default=None, max_length=10000)

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("summary may not be null")
        return _normalize_required_text(value)

    @field_validator("evidence_status")
    @classmethod
    def reject_null_evidence_status(
        cls,
        value: EvidenceStatus | None,
    ) -> EvidenceStatus:
        if value is None:
            raise ValueError("evidence_status may not be null")
        return value

    @field_validator("verification_notes")
    @classmethod
    def normalize_verification_notes(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> CompletionReportUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self
