"""harden document integrity

Revision ID: 0002_document_integrity
Revises: 2dc9e9936fec
Create Date: 2026-11-04 11:36:55.281927

Enforces NULLS NOT DISTINCT document version uniqueness and makes new
documents inactive by default. Existing document rows are not modified by
the default change.

PostgreSQL 15+ is required for NULLS NOT DISTINCT uniqueness.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = '0002_document_integrity'
down_revision: str | None = '2dc9e9936fec'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENT_VERSION_CONSTRAINT = "uq_documents_manufacturer_model_name_version"


def _assert_no_null_version_duplicates() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT manufacturer, model, document_name, count(*) "
            "FROM documents "
            "WHERE version IS NULL "
            "GROUP BY manufacturer, model, document_name "
            "HAVING count(*) > 1"
        )
    ).fetchall()

    if rows:
        duplicates = "; ".join(
            f"{manufacturer}/{model}/{document_name} "
            f"({count} rows)"
            for manufacturer, model, document_name, count in rows
        )
        raise RuntimeError(
            "Cannot enforce NULLS NOT DISTINCT document versions: "
            "duplicate documents with a NULL version exist and must be "
            f"reviewed before migrating: {duplicates}"
        )


def upgrade() -> None:
    if not context.is_offline_mode():
        _assert_no_null_version_duplicates()

    op.drop_constraint(
        DOCUMENT_VERSION_CONSTRAINT,
        "documents",
        type_="unique",
    )
    op.create_unique_constraint(
        DOCUMENT_VERSION_CONSTRAINT,
        "documents",
        ["manufacturer", "model", "document_name", "version"],
        postgresql_nulls_not_distinct=True,
    )
    op.alter_column(
        "documents",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.text("false"),
    )


def downgrade() -> None:
    op.alter_column(
        "documents",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.text("true"),
    )
    op.drop_constraint(
        DOCUMENT_VERSION_CONSTRAINT,
        "documents",
        type_="unique",
    )
    op.create_unique_constraint(
        DOCUMENT_VERSION_CONSTRAINT,
        "documents",
        ["manufacturer", "model", "document_name", "version"],
    )
