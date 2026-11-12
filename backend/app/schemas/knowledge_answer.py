from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings


class AnswerStatus(str, Enum):
    """Outcome of a knowledge answer request.

    - ``answered``: a grounded answer was produced from retrieved evidence.
    - ``insufficient_evidence``: the indexed documentation did not contain
      enough relevant information to answer the question.
    - ``conflicting_evidence``: retrieved sources contradict one another, so no
      single documented answer can be selected without an unsupported
      assumption.
    """

    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class KnowledgeAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    manufacturer: str | None = Field(default=None, max_length=150)
    model: str | None = Field(default=None, max_length=150)
    top_k: int = Field(
        default=settings.retrieval_default_top_k,
        ge=1,
        le=settings.retrieval_max_top_k,
    )

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Question must not be blank")
        return stripped

    @field_validator("manufacturer", "model")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class CitationResponse(BaseModel):
    """A citation constructed from a retrieved chunk.

    Every field is copied from the authoritative retrieval result. The model
    only supplies the stable ``source_id``; it cannot introduce document IDs,
    titles, page numbers or excerpts that were not retrieved.
    """

    source_id: str
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    manufacturer: str
    model: str
    version: str | None = None
    page_number: int | None = None
    chunk_index: int
    excerpt: str


class KnowledgeAnswerResponse(BaseModel):
    answer: str
    status: AnswerStatus
    citations: list[CitationResponse]
    evidence_summary: str | None = None
    insufficient_evidence: bool
    missing_information: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
