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

from app.models.enums import Priority, WorkOrderStatus


class WorkOrderResponse(BaseModel):
    id: uuid.UUID
    complaint_id: uuid.UUID
    equipment_id: uuid.UUID
    title: str
    description: str
    diagnostic_checklist: list[Any]
    priority: Priority
    status: WorkOrderStatus
    created_at: datetime
    updated_at: datetime


class WorkOrderListResponse(BaseModel):
    items: list[WorkOrderResponse]
    total: int
    limit: int
    offset: int


class WorkOrderCreate(BaseModel):
    """Create a work order from an eligible complaint.

    The complaint, equipment and complaint owner are derived from the URL and
    database. They are intentionally absent so a client cannot forge them.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    diagnostic_checklist: list[Any] = Field(default_factory=list)
    priority: Priority | None = None

    @field_validator("title", "description")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field must not be blank")
        return stripped


class WorkOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    description: str | None = Field(
        default=None,
        min_length=1,
        max_length=10000,
    )
    diagnostic_checklist: list[Any] | None = None
    priority: Priority | None = None

    @field_validator("title", "description")
    @classmethod
    def normalize_required_text(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Field may not be null")
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field must not be blank")
        return stripped

    @field_validator("diagnostic_checklist", "priority")
    @classmethod
    def reject_null_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field may not be null")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> WorkOrderUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class WorkOrderStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: WorkOrderStatus
