"""stage document chunk replacement safely

Revision ID: 0013_staged_document_chunks
Revises: 0012_document_embeddings
Create Date: 2026-11-11 00:00:00.000000

Adds ``is_current`` to ``document_chunks`` so a replacement ingestion can
insert its new chunk set without deleting the previous valid set. The previous
set is only removed after the replacement chunks and embeddings have both been
written successfully.

The original ``(document_id, chunk_index)`` unique constraint is replaced by a
partial unique index that only applies to current chunks. Staged chunks may
therefore reuse the same chunk indexes as the current set while an ingestion is
in progress, and promotion becomes a single transactional swap.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_staged_document_chunks"
down_revision: str | None = "0012_document_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHUNKS_TABLE_NAME = "document_chunks"
LEGACY_UNIQUE_NAME = "uq_document_chunks_document_id_chunk_index"
CURRENT_UNIQUE_NAME = "uq_document_chunks_document_id_chunk_index_current"
CURRENT_LOOKUP_NAME = "ix_document_chunks_document_id_is_current"


def upgrade() -> None:
    op.add_column(
        CHUNKS_TABLE_NAME,
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.drop_constraint(
        LEGACY_UNIQUE_NAME,
        CHUNKS_TABLE_NAME,
        type_="unique",
    )
    op.create_index(
        CURRENT_UNIQUE_NAME,
        CHUNKS_TABLE_NAME,
        ["document_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        CURRENT_LOOKUP_NAME,
        CHUNKS_TABLE_NAME,
        ["document_id", "is_current"],
        unique=False,
    )


def downgrade() -> None:
    # Staged chunks are incomplete replacements; current chunks are authoritative.
    op.execute(
        f'DELETE FROM "{CHUNKS_TABLE_NAME}" WHERE "is_current" IS FALSE'
    )
    op.drop_index(CURRENT_LOOKUP_NAME, table_name=CHUNKS_TABLE_NAME)
    op.drop_index(CURRENT_UNIQUE_NAME, table_name=CHUNKS_TABLE_NAME)
    op.create_unique_constraint(
        LEGACY_UNIQUE_NAME,
        CHUNKS_TABLE_NAME,
        ["document_id", "chunk_index"],
    )
    op.drop_column(CHUNKS_TABLE_NAME, "is_current")
