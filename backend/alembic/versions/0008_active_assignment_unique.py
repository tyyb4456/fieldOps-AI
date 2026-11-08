"""enforce one active assignment per work order

Revision ID: 0008_active_assignment_unique
Revises: 0007_complaint_history_sequence
Create Date: 2026-11-07 11:00:00.000000

A work order may accumulate assignment attempts over time, but it must never
have more than one active (offered or accepted) assignment. Service-layer
transactions lock the work-order row before changing assignment state; this
partial unique index is the database backstop for any future write path that
bypasses that lock.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0008_active_assignment_unique"
down_revision: str | None = "0007_complaint_history_sequence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE_ASSIGNMENT_INDEX = "uq_technician_assignments_active_work_order"

_ACTIVE_ASSIGNMENT_PREDICATE = (
    "assignment_status IN ('offered', 'accepted')"
)

_DUPLICATE_ACTIVE_SQL = """
SELECT work_order_id, count(*) AS active_count
FROM technician_assignments
WHERE assignment_status IN ('offered', 'accepted')
GROUP BY work_order_id
HAVING count(*) > 1
LIMIT 1
"""


def upgrade() -> None:
    connection = op.get_bind()
    duplicate = connection.execute(
        sa.text(_DUPLICATE_ACTIVE_SQL)
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot enforce one active assignment per work order: "
            f"work_order_id {duplicate.work_order_id} has "
            f"{duplicate.active_count} active assignments. Withdraw or "
            "reject the extra assignments, then rerun the migration."
        )

    op.create_index(
        ACTIVE_ASSIGNMENT_INDEX,
        "technician_assignments",
        ["work_order_id"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_ASSIGNMENT_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index(
        ACTIVE_ASSIGNMENT_INDEX,
        table_name="technician_assignments",
        postgresql_where=sa.text(_ACTIVE_ASSIGNMENT_PREDICATE),
    )
