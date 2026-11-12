from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.knowledge_answer import CitationResponse


class DiagnosticStatus(str, Enum):
    """Outcome of a technical diagnostic investigation.

    - ``diagnosed``: cited documentation supports a probable diagnosis.
    - ``needs_more_information``: the investigation cannot proceed without
      missing complaint or equipment information.
    - ``insufficient_evidence``: no reliable documentation or service evidence
      supports a diagnosis.
    - ``conflicting_evidence``: available sources contradict one another, so no
      single diagnosis is selected.
    """

    DIAGNOSED = "diagnosed"
    NEEDS_MORE_INFORMATION = "needs_more_information"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"


class DiagnosticInvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    complaint_id: uuid.UUID
    focus: str | None = Field(default=None, max_length=2000)

    @field_validator("focus")
    @classmethod
    def normalize_focus(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class DiagnosticCauseResponse(BaseModel):
    cause: str
    basis: str
    evidence_chunk_ids: list[uuid.UUID] = Field(default_factory=list)


class DiagnosticCheckResponse(BaseModel):
    step: str
    safety_note: str | None = None
    evidence_chunk_ids: list[uuid.UUID] = Field(default_factory=list)


class DiagnosticInvestigationResponse(BaseModel):
    complaint_id: uuid.UUID
    status: DiagnosticStatus
    summary: str
    probable_causes: list[DiagnosticCauseResponse] = Field(default_factory=list)
    recommended_checks: list[DiagnosticCheckResponse] = Field(
        default_factory=list
    )
    missing_information: list[str] = Field(default_factory=list)
    safety_warnings: list[str] = Field(default_factory=list)
    conflicting_evidence_notes: list[str] = Field(default_factory=list)
    requires_escalation: bool
    escalation_reason: str | None = None
    citations: list[CitationResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str
