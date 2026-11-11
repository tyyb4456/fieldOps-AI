from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class RetrievalSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    manufacturer: str | None = Field(default=None, max_length=150)
    model: str | None = Field(default=None, max_length=150)
    top_k: int = Field(
        default=settings.retrieval_default_top_k,
        ge=1,
        le=settings.retrieval_max_top_k,
    )

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Query must not be blank")
        return stripped

    @field_validator("manufacturer", "model")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class RetrievalResultResponse(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    manufacturer: str
    model: str
    version: str | None = None
    page_number: int | None = None
    chunk_index: int
    content: str
    distance: float
    similarity: float


class RetrievalSearchResponse(BaseModel):
    items: list[RetrievalResultResponse]
    top_k: int
