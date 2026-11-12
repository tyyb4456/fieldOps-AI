"""normalize stored email addresses

Revision ID: 0004_normalize_emails
Revises: 0003_clerk_identity
Create Date: 2026-11-05 10:00:00.000000

Email comparison is case-insensitive in the application. Existing rows are
normalized so the existing unique constraint behaves consistently.

If two existing accounts differ only by case or surrounding whitespace, this
migration aborts rather than merging accounts. An operator must resolve the
conflict deliberately.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_normalize_emails"
down_revision: str | None = "0003_clerk_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _assert_no_case_insensitive_duplicates() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT lower(btrim(email)) AS normalized_email, "
            "count(*) AS account_count "
            "FROM users "
            "WHERE email IS NOT NULL AND btrim(email) <> '' "
            "GROUP BY lower(btrim(email)) "
            "HAVING count(*) > 1"
        )
    ).all()

    if rows:
        addresses = ", ".join(row.normalized_email for row in rows)
        raise RuntimeError(
            "Cannot normalize user emails because multiple local accounts "
            "share a case-insensitive email address: "
            f"{addresses}. Resolve these duplicate accounts manually."
        )


def upgrade() -> None:
    _assert_no_case_insensitive_duplicates()

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE users SET email = NULL "
            "WHERE email IS NOT NULL AND btrim(email) = ''"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE users "
            "SET email = lower(btrim(email)) "
            "WHERE email IS NOT NULL "
            "AND email <> lower(btrim(email))"
        )
    )


def downgrade() -> None:
    # Normalization is intentionally lossy: the original casing and
    # whitespace are not retained, so there is no safe automatic reversal.
    pass
