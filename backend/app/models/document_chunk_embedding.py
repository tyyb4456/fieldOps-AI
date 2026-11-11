from __future__ import annotations

import uuid
from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import DEFAULT_EMBEDDING_DIMENSIONS
from app.db.base import Base

VECTOR_TABLE_NAME = "document_chunk_embeddings"
VECTOR_INDEX_NAME = "ix_document_chunk_embeddings_embedding_hnsw"
VECTOR_DOCUMENT_INDEX_NAME = "ix_document_chunk_embeddings_document_id"
VECTOR_MODEL_INDEX_NAME = "ix_document_chunk_embeddings_embedding_model"
VECTOR_DISTANCE_OPERATOR_CLASS = "vector_cosine_ops"
VECTOR_INDEX_M = 16
VECTOR_INDEX_EF_CONSTRUCTION = 64


class DocumentChunkEmbedding(Base):
    __tablename__ = VECTOR_TABLE_NAME
    __table_args__ = (
        Index(VECTOR_DOCUMENT_INDEX_NAME, "document_id"),
        Index(VECTOR_MODEL_INDEX_NAME, "embedding_model"),
        Index(
            VECTOR_INDEX_NAME,
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": VECTOR_DISTANCE_OPERATOR_CLASS},
            postgresql_with={
                "m": VECTOR_INDEX_M,
                "ef_construction": VECTOR_INDEX_EF_CONSTRUCTION,
            },
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(DEFAULT_EMBEDDING_DIMENSIONS),
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    embedding_metadata: Mapped[dict[str, Any]] = mapped_column(
        "langchain_metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    def __repr__(self) -> str:
        return (
            "DocumentChunkEmbedding("
            f"id={self.id!r}, "
            f"document_id={self.document_id!r})"
        )
