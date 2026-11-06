"""track bounded Clerk profile enrichment

Revision ID: 0005_profile_enrichment
Revises: 0004_normalize_emails
Create Date: 2026-11-05 10:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_profile_enrichment"
down_revision: str | None = "0004_normalize_emails"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "profile_enrichment_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "profile_enrichment_last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "profile_enriched_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "profile_enriched_at")
    op.drop_column("users", "profile_enrichment_last_attempt_at")
    op.drop_column("users", "profile_enrichment_attempts")
