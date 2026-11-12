"""add distinct complaint cancellation status and append-only history

Revision ID: 0006_complaint_lifecycle
Revises: 0005_profile_enrichment
Create Date: 2026-11-06 09:00:00.000000

Customer cancellation previously reused the internal ``closed`` status.
This migration introduces a distinct ``cancelled`` status and records an
append-only history entry for every complaint mutation.

All existing ``closed`` complaints were produced by the cancellation
endpoint, which was the only code path that set that status, so they are
backfilled to ``cancelled``.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_complaint_lifecycle"
down_revision: str | None = "0005_profile_enrichment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMPLAINT_STATUS_CONSTRAINT = "ck_complaints_complaint_status"

COMPLAINT_STATUSES = (
    "received",
    "analyzing",
    "awaiting_customer",
    "ready_for_work_order",
    "converted",
    "escalated",
    "closed",
    "cancelled",
)

_STATUS_IN_SQL = "status IN (" + ", ".join(
    f"'{value}'" for value in COMPLAINT_STATUSES
) + ")"

_HISTORY_FROM_ENUM = sa.Enum(
    *COMPLAINT_STATUSES,
    name="complaint_history_from_status",
    native_enum=False,
    create_constraint=True,
    length=40,
)
_HISTORY_TO_ENUM = sa.Enum(
    *COMPLAINT_STATUSES,
    name="complaint_history_to_status",
    native_enum=False,
    create_constraint=True,
    length=40,
)


def upgrade() -> None:
    op.drop_constraint(
        op.f(COMPLAINT_STATUS_CONSTRAINT),
        "complaints",
        type_="check",
    )
    op.execute(
        "UPDATE complaints SET status = 'cancelled' "
        "WHERE status = 'closed'"
    )
    op.create_check_constraint(
        op.f(COMPLAINT_STATUS_CONSTRAINT),
        "complaints",
        _STATUS_IN_SQL,
    )

    op.create_table(
        "complaint_history",
        sa.Column("complaint_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_status", _HISTORY_FROM_ENUM, nullable=True),
        sa.Column("to_status", _HISTORY_TO_ENUM, nullable=True),
        sa.Column(
            "changed_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["complaint_id"],
            ["complaints.id"],
            name=op.f("fk_complaint_history_complaint_id_complaints"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_complaint_history_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_complaint_history")),
    )
    op.create_index(
        "ix_complaint_history_complaint_id",
        "complaint_history",
        ["complaint_id"],
        unique=False,
    )
    op.create_index(
        "ix_complaint_history_created_at",
        "complaint_history",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_complaint_history_created_at",
        table_name="complaint_history",
    )
    op.drop_index(
        "ix_complaint_history_complaint_id",
        table_name="complaint_history",
    )
    op.drop_table("complaint_history")

    op.drop_constraint(
        op.f(COMPLAINT_STATUS_CONSTRAINT),
        "complaints",
        type_="check",
    )
    op.execute(
        "UPDATE complaints SET status = 'closed' "
        "WHERE status = 'cancelled'"
    )
    op.create_check_constraint(
        op.f(COMPLAINT_STATUS_CONSTRAINT),
        "complaints",
        "status IN ("
        + ", ".join(
            f"'{value}'"
            for value in COMPLAINT_STATUSES
            if value != "cancelled"
        )
        + ")",
    )
