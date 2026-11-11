"""add pgvector document chunk embeddings

Revision ID: 0012_document_embeddings
Revises: 0011_document_integrity
Create Date: 2026-11-10 00:00:00.000000

Creates the ``vector`` extension and the LangChain-compatible embedding table
used for retrieval. The table is owned by Alembic and references
``document_chunks`` with ``ON DELETE CASCADE`` so removing or re-ingesting a
document cannot leave stale vectors behind.

This migration intentionally does not backfill embeddings. Existing documents
must be re-ingested after ``GOOGLE_API_KEY`` is configured to become
retrievable. Downgrade drops the embedding table but leaves the ``vector``
extension installed because other objects may depend on it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012_document_embeddings"
down_revision: str | None = "0011_document_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSIONS = 1536
VECTOR_TABLE_NAME = "document_chunk_embeddings"
VECTOR_DOCUMENT_INDEX_NAME = "ix_document_chunk_embeddings_document_id"
VECTOR_MODEL_INDEX_NAME = "ix_document_chunk_embeddings_embedding_model"
VECTOR_HNSW_INDEX_NAME = "ix_document_chunk_embeddings_embedding_hnsw"
VECTOR_FK_NAME = "fk_document_chunk_embeddings_id_document_chunks"
DOCUMENTS_TABLE_NAME = "documents"
DOCUMENTS_MODEL_INDEX_NAME = "ix_documents_embedding_model"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        VECTOR_TABLE_NAME,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "embedding",
            Vector(EMBEDDING_DIMENSIONS),
            nullable=False,
        ),
        sa.Column(
            "embedding_model",
            sa.String(100),
            nullable=False,
        ),
        sa.Column(
            "langchain_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(
            ["id"],
            ["document_chunks.id"],
            name=VECTOR_FK_NAME,
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunk_embeddings"),
    )
    op.create_index(
        VECTOR_DOCUMENT_INDEX_NAME,
        VECTOR_TABLE_NAME,
        ["document_id"],
        unique=False,
    )
    op.create_index(
        VECTOR_MODEL_INDEX_NAME,
        VECTOR_TABLE_NAME,
        ["embedding_model"],
        unique=False,
    )
    op.create_index(
        VECTOR_HNSW_INDEX_NAME,
        VECTOR_TABLE_NAME,
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_with={"m": 16, "ef_construction": 64},
    )
    op.add_column(
        DOCUMENTS_TABLE_NAME,
        sa.Column(
            "embedding_model",
            sa.String(100),
            nullable=True,
        ),
    )
    op.create_index(
        DOCUMENTS_MODEL_INDEX_NAME,
        DOCUMENTS_TABLE_NAME,
        ["embedding_model"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        DOCUMENTS_MODEL_INDEX_NAME,
        table_name=DOCUMENTS_TABLE_NAME,
    )
    op.drop_column(DOCUMENTS_TABLE_NAME, "embedding_model")
    op.drop_index(
        VECTOR_HNSW_INDEX_NAME,
        table_name=VECTOR_TABLE_NAME,
    )
    op.drop_index(
        VECTOR_MODEL_INDEX_NAME,
        table_name=VECTOR_TABLE_NAME,
    )
    op.drop_index(
        VECTOR_DOCUMENT_INDEX_NAME,
        table_name=VECTOR_TABLE_NAME,
    )
    op.drop_table(VECTOR_TABLE_NAME)
