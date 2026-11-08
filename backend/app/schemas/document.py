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
    file_path: str
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


class DocumentCreate(BaseModel):
    """Register document metadata.

    Binary content and document chunks are not accepted here. New documents
    start inactive and must be explicitly approved by an administrator.
    """

    model_config = ConfigDict(extra="forbid")

    manufacturer: str = Field(min_length=1, max_length=150)
    model: str = Field(min_length=1, max_length=150)
    document_name: str = Field(min_length=1, max_length=255)
    version: str | None = Field(default=None, max_length=100)
    file_path: str = Field(min_length=1, max_length=2000)

    @field_validator(
        "manufacturer",
        "model",
        "document_name",
        "file_path",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return _normalize_required_text(value)

    @field_validator("version")
    @classmethod
    def normalize_version(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


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
    file_path: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
    )
    is_active: bool | None = None

    @field_validator(
        "manufacturer",
        "model",
        "document_name",
        "file_path",
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

    @field_validator("is_active")
    @classmethod
    def reject_null_is_active(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("is_active may not be null")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> DocumentUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self
