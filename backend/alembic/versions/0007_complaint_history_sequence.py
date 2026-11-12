"""add deterministic per-complaint history sequencing

Revision ID: 0007_complaint_history_sequence
Revises: 0006_complaint_lifecycle
Create Date: 2026-11-07 10:00:00.000000

``complaint_history.created_at`` is populated by PostgreSQL ``now()``, which
is the transaction start time, not the moment an event actually occurred.
That makes wall-clock timestamps unreliable for ordering events written by
concurrent transactions. This migration adds a per-complaint
``sequence_number`` and a unique ``(complaint_id, sequence_number)``
constraint so history has a deterministic order.

Existing rows are backfilled with ``ROW_NUMBER()`` partitioned by
``complaint_id`` and ordered by ``(created_at, id)``. This establishes a
deterministic historical ordering; it cannot recover the original real-world
order of events that were recorded before the sequence existed.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_complaint_history_sequence"
down_revision: str | None = "0006_complaint_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEQUENCE_UNIQUE_CONSTRAINT = "uq_complaint_history_complaint_sequence"

_BACKFILL_SEQUENCE_SQL = """
UPDATE complaint_history AS history
SET sequence_number = ranked.sequence_number
FROM (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY complaint_id
            ORDER BY created_at ASC, id ASC
        ) AS sequence_number
    FROM complaint_history
) AS ranked
WHERE history.id = ranked.id
"""

_DOWNGRADE_REFUSAL = (
    "Refusing to downgrade: complaint_history contains {count} audit "
    "record(s). Dropping sequence_number would destroy the deterministic "
    "history order, and continuing on to 0005 drops the entire "
    "complaint_history table and converts 'cancelled' back to 'closed', "
    "erasing the cancellation/closure distinction. Export and verify the "
    "history first (for example: COPY (SELECT * FROM complaint_history "
    "ORDER BY complaint_id, sequence_number) TO ... WITH CSV HEADER), then "
    "deliberately truncate complaint_history in a maintenance window before "
    "retrying the downgrade. See _docs/database_integrity_conventions.md "
    "sections 4 and 5."
)


def upgrade() -> None:
    op.add_column(
        "complaint_history",
        sa.Column("sequence_number", sa.Integer(), nullable=True),
    )
    op.execute(_BACKFILL_SEQUENCE_SQL)
    op.alter_column(
        "complaint_history",
        "sequence_number",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_unique_constraint(
        op.f(SEQUENCE_UNIQUE_CONSTRAINT),
        "complaint_history",
        ["complaint_id", "sequence_number"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    history_count = connection.execute(
        sa.text("SELECT count(*) FROM complaint_history")
    ).scalar_one()
    if history_count:
        raise RuntimeError(_DOWNGRADE_REFUSAL.format(count=history_count))

    op.drop_constraint(
        op.f(SEQUENCE_UNIQUE_CONSTRAINT),
        "complaint_history",
        type_="unique",
    )
    op.drop_column("complaint_history", "sequence_number")
