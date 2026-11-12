"""add document storage and ingestion foundation

Revision ID: 0010_document_storage
Revises: 0009_completion_report_link
Create Date: 2026-11-08 12:00:00.000000

Legacy ``documents.file_path`` values are preserved but are not trusted as
storage keys. Existing rows are kept, deactivated, and left in ``pending``
ingestion state because their binary content cannot be verified. Operators
must re-upload legacy documents before they can be activated.

Downgrade refuses to run while storage-backed documents exist. Those rows
would lose their trusted storage metadata and could leave orphaned files, so
they must be archived or removed deliberately first.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_document_storage"
down_revision: str | None = "0009_completion_report_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STORAGE_KEY_UNIQUE = "uq_documents_storage_key"
INGESTION_STATUS_INDEX = "ix_documents_ingestion_status"
UPLOADED_BY_FK = "fk_documents_uploaded_by_id_users"
BYTE_SIZE_CHECK = "ck_documents_byte_size_non_negative"
CHECKSUM_CHECK = "ck_documents_checksum_sha256_length"
ACTIVE_CHECK = "ck_documents_active_requires_ready"
STATUS_CHECK = "ck_documents_ingestion_status"


def _assert_downgrade_safe() -> None:
    bind = op.get_bind()
    unsafe = bind.execute(
        sa.text(
            "SELECT count(*) FROM documents "
            "WHERE storage_key IS NOT NULL OR file_path IS NULL"
        )
    ).scalar_one()
    if unsafe:
        raise RuntimeError(
            "Refusing to downgrade document storage migration: "
            f"{unsafe} storage-backed document(s) exist. Archive or remove "
            "them and their stored files before downgrading."
        )


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("storage_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("original_filename", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("content_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("uploaded_by_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "ingestion_status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "documents",
        sa.Column("ingestion_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.alter_column(
        "documents",
        "file_path",
        existing_type=sa.Text(),
        existing_nullable=False,
        nullable=True,
    )

    op.execute(
        sa.text(
            "UPDATE documents "
            "SET is_active = false, ingestion_status = 'pending'"
        )
    )

    op.create_check_constraint(
        op.f(STATUS_CHECK),
        "documents",
        "ingestion_status IN ('pending', 'processing', 'ready', 'failed')",
    )
    op.create_check_constraint(
        op.f(BYTE_SIZE_CHECK),
        "documents",
        "byte_size IS NULL OR byte_size >= 0",
    )
    op.create_check_constraint(
        op.f(CHECKSUM_CHECK),
        "documents",
        "checksum_sha256 IS NULL OR length(checksum_sha256) = 64",
    )
    op.create_check_constraint(
        op.f(ACTIVE_CHECK),
        "documents",
        "is_active = false OR ingestion_status = 'ready'",
    )
    op.create_unique_constraint(
        STORAGE_KEY_UNIQUE,
        "documents",
        ["storage_key"],
    )
    op.create_index(
        INGESTION_STATUS_INDEX,
        "documents",
        ["ingestion_status"],
    )
    op.create_foreign_key(
        UPLOADED_BY_FK,
        "documents",
        "users",
        ["uploaded_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    _assert_downgrade_safe()

    op.drop_constraint(UPLOADED_BY_FK, "documents", type_="foreignkey")
    op.drop_index(INGESTION_STATUS_INDEX, table_name="documents")
    op.drop_constraint(
        STORAGE_KEY_UNIQUE,
        "documents",
        type_="unique",
    )
    op.drop_constraint(
        op.f(ACTIVE_CHECK),
        "documents",
        type_="check",
    )
    op.drop_constraint(
        op.f(CHECKSUM_CHECK),
        "documents",
        type_="check",
    )
    op.drop_constraint(
        op.f(BYTE_SIZE_CHECK),
        "documents",
        type_="check",
    )
    op.drop_constraint(
        op.f(STATUS_CHECK),
        "documents",
        type_="check",
    )

    op.drop_column("documents", "ingested_at")
    op.drop_column("documents", "ingestion_error")
    op.drop_column("documents", "ingestion_status")
    op.drop_column("documents", "uploaded_by_id")
    op.drop_column("documents", "checksum_sha256")
    op.drop_column("documents", "byte_size")
    op.drop_column("documents", "content_type")
    op.drop_column("documents", "original_filename")
    op.drop_column("documents", "storage_key")

    op.alter_column(
        "documents",
        "file_path",
        existing_type=sa.Text(),
        existing_nullable=True,
        nullable=False,
    )
