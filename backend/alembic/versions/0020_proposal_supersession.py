"""add proposal supersession state

Revision ID: 0020_proposal_supersession
Revises: 0019_message_idempotency
Create Date: 2026-11-18 00:00:00.000000

Step 4.13.2 represents deterministic invalidation of a pending work-order
proposal without falsely recording a human rejection. A proposal that leaves
``pending_approval`` because the complaint left ``ready_for_work_order`` is
``superseded``; the existing ``reviewed_by_id``/``reviewed_at``/
``rejection_reason`` columns keep their human-review meaning and are untouched.

The status column is a non-native SQL enum with ``create_constraint=True``, so
the CHECK constraint is dropped and recreated with the new value. The partial
unique pending index needs no change because ``superseded`` rows are not
``pending_approval``.

The downgrade refuses to run while superseded rows exist, because the previous
schema cannot represent them without mislabeling them as human decisions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020_proposal_supersession"
down_revision: str | None = "0019_message_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROPOSAL_TABLE = "work_order_proposals"
PROPOSAL_STATUS_CONSTRAINT = "ck_work_order_proposals_work_order_proposal_status"
SUPERSEDED_BY_FK = "fk_work_order_proposals_superseded_by_id_users"

OLD_STATUSES = (
    "pending_approval",
    "approved",
    "rejected",
)
NEW_STATUSES = (
    "pending_approval",
    "approved",
    "rejected",
    "superseded",
)


def _status_check(values: Sequence[str]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"status IN ({rendered})"


def upgrade() -> None:
    op.add_column(
        PROPOSAL_TABLE,
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        PROPOSAL_TABLE,
        sa.Column("superseded_by_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        PROPOSAL_TABLE,
        sa.Column("supersession_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        SUPERSEDED_BY_FK,
        PROPOSAL_TABLE,
        "users",
        ["superseded_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        op.f(PROPOSAL_STATUS_CONSTRAINT),
        PROPOSAL_TABLE,
        type_="check",
    )
    op.create_check_constraint(
        op.f(PROPOSAL_STATUS_CONSTRAINT),
        PROPOSAL_TABLE,
        _status_check(NEW_STATUSES),
    )


def downgrade() -> None:
    connection = op.get_bind()
    superseded_count = connection.execute(
        sa.text(f"SELECT count(*) FROM {PROPOSAL_TABLE} WHERE status = 'superseded'")
    ).scalar_one()
    if superseded_count:
        raise RuntimeError(
            "Refusing to downgrade: superseded proposals cannot be represented "
            "by the previous status constraint. Archive or re-review them "
            "before downgrading."
        )

    op.drop_constraint(
        op.f(PROPOSAL_STATUS_CONSTRAINT),
        PROPOSAL_TABLE,
        type_="check",
    )
    op.create_check_constraint(
        op.f(PROPOSAL_STATUS_CONSTRAINT),
        PROPOSAL_TABLE,
        _status_check(OLD_STATUSES),
    )

    op.drop_constraint(SUPERSEDED_BY_FK, PROPOSAL_TABLE, type_="foreignkey")
    op.drop_column(PROPOSAL_TABLE, "supersession_reason")
    op.drop_column(PROPOSAL_TABLE, "superseded_by_id")
    op.drop_column(PROPOSAL_TABLE, "superseded_at")
