"""harden document checksum format and track ingestion start
Revision ID: 0011_document_integrity
Revises: 0010_document_storage
Create Date: 2026-11-09 00:00:00.000000

Adds ``documents.ingestion_started_at`` for stale-ingestion recovery and
tightens the checksum check from a length test to an exact lowercase SHA-256
format test. Existing checksums must already be valid; the migration fails
closed rather than rewriting untrusted values.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_document_integrity"
down_revision: str | None = "0010_document_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_CHECKSUM_CHECK = "ck_documents_checksum_sha256_length"
NEW_CHECKSUM_CHECK = "ck_documents_checksum_sha256_format"
CHECKSUM_PATTERN = "^[0-9a-f]{64}$"


def _assert_existing_checksums_are_valid() -> None:
    bind = op.get_bind()
    invalid = bind.execute(
        sa.text(
            "SELECT count(*) FROM documents "
            "WHERE checksum_sha256 IS NOT NULL "
            "AND checksum_sha256 !~ :pattern"
        ),
        {"pattern": CHECKSUM_PATTERN},
    ).scalar_one()
    if invalid:
        raise RuntimeError(
            "Refusing to tighten document checksum validation: "
            f"{invalid} existing checksum(s) are not lowercase SHA-256 "
            "hexadecimal values. Correct or clear them deliberately first."
        )


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "ingestion_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    _assert_existing_checksums_are_valid()

    op.drop_constraint(
        op.f(OLD_CHECKSUM_CHECK),
        "documents",
        type_="check",
    )
    op.create_check_constraint(
        op.f(NEW_CHECKSUM_CHECK),
        "documents",
        f"checksum_sha256 IS NULL OR checksum_sha256 ~ '{CHECKSUM_PATTERN}'",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f(NEW_CHECKSUM_CHECK),
        "documents",
        type_="check",
    )
    op.create_check_constraint(
        op.f(OLD_CHECKSUM_CHECK),
        "documents",
        "checksum_sha256 IS NULL OR length(checksum_sha256) = 64",
    )

    op.drop_column("documents", "ingestion_started_at")
