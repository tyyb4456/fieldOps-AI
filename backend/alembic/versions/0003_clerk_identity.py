"""add clerk identity mapping

Revision ID: 0003_clerk_identity
Revises: 0002_document_integrity
Create Date: 2026-11-04 14:00:00.000000

Adds a stable external Clerk identity to local users and makes the legacy
password_hash column nullable because Clerk owns authentication credentials.
Existing users keep their data and are not linked to a Clerk identity
automatically.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_clerk_identity"
down_revision: str | None = "0002_document_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLERK_USER_ID_CONSTRAINT = "uq_users_clerk_user_id"


def _assert_no_null_password_hashes() -> None:
    bind = op.get_bind()
    null_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM users WHERE password_hash IS NULL"
        )
    ).scalar_one()

    if null_count:
        raise RuntimeError(
            "Cannot restore the NOT NULL password_hash constraint: "
            f"{null_count} user(s) have no password hash. Clerk-provisioned "
            "users must be reviewed before downgrading this migration."
        )


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("clerk_user_id", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        CLERK_USER_ID_CONSTRAINT,
        "users",
        ["clerk_user_id"],
    )
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.Text(),
        existing_nullable=False,
        nullable=True,
    )


def downgrade() -> None:
    _assert_no_null_password_hashes()
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.Text(),
        existing_nullable=True,
        nullable=False,
    )
    op.drop_constraint(
        CLERK_USER_ID_CONSTRAINT,
        "users",
        type_="unique",
    )
    op.drop_column("users", "clerk_user_id")
