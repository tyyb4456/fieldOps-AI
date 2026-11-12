from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.models.enums import Priority, WorkOrderProposalStatus
from app.schemas.diagnostic import DiagnosticStatus
from app.schemas.knowledge_answer import CitationResponse


class TechnicianRecommendationResponse(BaseModel):
    technician_id: uuid.UUID
    full_name: str
    eligible: bool
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    active_workload: int
    availability_status: str
    reasons: list[str] = Field(default_factory=list)
    rank: int


class WorkOrderProposalResponse(BaseModel):
    id: uuid.UUID
    complaint_id: uuid.UUID
    status: WorkOrderProposalStatus
    title: str
    problem_description: str
    proposed_scope: str
    technical_findings: str
    recommended_actions: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    required_parts: list[str] = Field(default_factory=list)
    priority: Priority
    estimated_duration_minutes: int | None = None
    safety_warnings: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    generation_warnings: list[str] = Field(default_factory=list)
    diagnostic_status: DiagnosticStatus
    diagnostic_summary: str
    diagnostic_snapshot: dict[str, object] = Field(default_factory=dict)
    citations: list[CitationResponse] = Field(default_factory=list)
    requires_escalation: bool
    escalation_reason: str | None = None
    technician_recommendations: list[TechnicianRecommendationResponse] = Field(
        default_factory=list
    )
    selected_technician_id: uuid.UUID | None = None
    created_by_id: uuid.UUID | None = None
    reviewed_by_id: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    resulting_work_order_id: uuid.UUID | None = None
    resulting_assignment_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class WorkOrderProposalListResponse(BaseModel):
    items: list[WorkOrderProposalResponse]
    total: int
    limit: int
    offset: int


class WorkOrderProposalApproveRequest(BaseModel):
    """Human approval of an agent-prepared proposal.

    The reviewer may select any recommended technician. The service re-checks
    current eligibility and ignores no client-supplied work-order or complaint
    fields, which are derived from the persisted proposal and database.
    """

    model_config = ConfigDict(extra="forbid")

    technician_id: uuid.UUID | None = None


class WorkOrderProposalRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Reason must not be blank")
        return stripped
