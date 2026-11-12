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


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ServiceRecordResponse(BaseModel):
    id: uuid.UUID
    equipment_id: uuid.UUID
    work_order_id: uuid.UUID
    technician_id: uuid.UUID
    findings: str | None = None
    work_performed: str | None = None
    parts_used: list[Any]
    recorded_at: datetime


class ServiceRecordListResponse(BaseModel):
    items: list[ServiceRecordResponse]
    total: int
    limit: int
    offset: int


class ServiceRecordCreate(BaseModel):
    """Record service activity for an accepted, assigned work order.

    Technician, equipment, work order and recorded time are server-controlled
    and intentionally rejected if supplied by the client.
    """

    model_config = ConfigDict(extra="forbid")

    findings: str | None = Field(default=None, max_length=10000)
    work_performed: str | None = Field(default=None, max_length=10000)
    parts_used: list[Any] = Field(default_factory=list)

    @field_validator("findings", "work_performed")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def require_activity_description(self) -> ServiceRecordCreate:
        if not self.findings and not self.work_performed:
            raise ValueError(
                "At least one of findings or work_performed is required"
            )
        return self


class ServiceRecordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: str | None = Field(default=None, max_length=10000)
    work_performed: str | None = Field(default=None, max_length=10000)
    parts_used: list[Any] | None = None

    @field_validator("findings", "work_performed")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("parts_used")
    @classmethod
    def reject_null_parts_used(
        cls,
        value: list[Any] | None,
    ) -> list[Any]:
        if value is None:
            raise ValueError("parts_used may not be null")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> ServiceRecordUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self
