from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import IngestionStatus, enum_type

if TYPE_CHECKING:
    from app.models.document_chunk import DocumentChunk


class Document(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "manufacturer",
            "model",
            "document_name",
            "version",
            name="uq_documents_manufacturer_model_name_version",
            postgresql_nulls_not_distinct=True,
        ),
        UniqueConstraint(
            "storage_key",
            name="uq_documents_storage_key",
        ),
        CheckConstraint(
            "byte_size IS NULL OR byte_size >= 0",
            name="byte_size_non_negative",
        ),
        CheckConstraint(
            "checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="checksum_sha256_format",
        ),
        CheckConstraint(
            "is_active = false OR ingestion_status = 'ready'",
            name="active_requires_ready",
        ),
        Index("ix_documents_ingestion_status", "ingestion_status"),
        Index("ix_documents_embedding_model", "embedding_model"),
    )

    manufacturer: Mapped[str] = mapped_column(String(150), nullable=False)
    model: Mapped[str] = mapped_column(String(150), nullable=False)
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    content_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    byte_size: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    ingestion_status: Mapped[IngestionStatus] = mapped_column(
        enum_type(IngestionStatus, "ingestion_status", length=20),
        nullable=False,
        default=IngestionStatus.PENDING,
        server_default=IngestionStatus.PENDING.value,
    )
    ingestion_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ingestion_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    embedding_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"Document(id={self.id!r}, document_name={self.document_name!r})"
