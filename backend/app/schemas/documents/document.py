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

from app.models.enums import IngestionStatus


def _normalize_required_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Field must not be blank")
    return stripped


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class DocumentResponse(BaseModel):
    id: uuid.UUID
    manufacturer: str
    model: str
    document_name: str
    version: str | None = None
    original_filename: str | None = None
    content_type: str | None = None
    byte_size: int | None = None
    checksum_sha256: str | None = None
    uploaded_by_id: uuid.UUID | None = None
    ingestion_status: IngestionStatus
    ingestion_error: str | None = None
    ingested_at: datetime | None = None
    is_active: bool
    created_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int


class DocumentChunkResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    page_number: int | None = None
    metadata: dict[str, Any]


class DocumentChunkListResponse(BaseModel):
    items: list[DocumentChunkResponse]
    total: int
    limit: int
    offset: int


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manufacturer: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )
    model: str | None = Field(default=None, min_length=1, max_length=150)
    document_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    version: str | None = Field(default=None, max_length=100)

    @field_validator(
        "manufacturer",
        "model",
        "document_name",
    )
    @classmethod
    def normalize_required_text(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Field may not be null")
        return _normalize_required_text(value)

    @field_validator("version")
    @classmethod
    def normalize_version(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> DocumentUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self
