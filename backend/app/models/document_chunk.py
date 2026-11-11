from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document

CHUNK_CURRENT_UNIQUE_INDEX = (
    "uq_document_chunks_document_id_chunk_index_current"
)
CHUNK_CURRENT_LOOKUP_INDEX = "ix_document_chunks_document_id_is_current"


class DocumentChunk(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index(
            CHUNK_CURRENT_UNIQUE_INDEX,
            "document_id",
            "chunk_index",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index(
            CHUNK_CURRENT_LOOKUP_INDEX,
            "document_id",
            "is_current",
        ),
        CheckConstraint(
            "chunk_index >= 0",
            name="chunk_index_non_negative",
        ),
        CheckConstraint(
            "page_number IS NULL OR page_number > 0",
            name="page_number_positive",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    document: Mapped[Document] = relationship(back_populates="chunks")

    def __repr__(self) -> str:
        return (
            "DocumentChunk("
            f"id={self.id!r}, "
            f"document_id={self.document_id!r}, "
            f"chunk_index={self.chunk_index!r})"
        )
