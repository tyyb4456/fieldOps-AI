from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import AssignmentStatus


class AssignmentResponse(BaseModel):
    id: uuid.UUID
    work_order_id: uuid.UUID
    technician_id: uuid.UUID
    assignment_status: AssignmentStatus
    assigned_at: datetime
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None


class AssignmentListResponse(BaseModel):
    items: list[AssignmentResponse]
    total: int
    limit: int
    offset: int


class AssignmentCreate(BaseModel):
    """Offer a work order to a technician.

    The work-order id comes from the URL. The technician id is the only
    client-supplied value; ownership and eligibility are verified against the
    database.
    """

    model_config = ConfigDict(extra="forbid")

    technician_id: uuid.UUID


class TechnicianSummaryResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str | None = None
    skills: dict[str, Any]
    service_area: str | None = None
    is_available: bool


class TechnicianListResponse(BaseModel):
    items: list[TechnicianSummaryResponse]
    total: int
    limit: int
    offset: int
