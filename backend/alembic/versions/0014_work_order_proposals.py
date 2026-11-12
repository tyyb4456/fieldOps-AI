"""add persisted work-order proposals

Revision ID: 0014_work_order_proposals
Revises: 0013_staged_document_chunks
Create Date: 2026-11-12 00:00:00.000000

Step 4.7 persists the agent-prepared work-order proposal before human review.
A proposal is separate from a work order: approval is the only path that
creates a work order, and every action still goes through the existing
deterministic work-order and assignment services.

A partial unique index prevents two pending proposals for the same complaint.
The resulting work-order reference is unique so one proposal cannot claim two
work orders and one work order cannot be linked to multiple proposals.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_work_order_proposals"
down_revision: str | None = "0013_staged_document_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROPOSAL_STATUS_ENUM = "work_order_proposal_status"
PRIORITY_ENUM = "work_order_priority"
PENDING_INDEX = "uq_work_order_proposals_pending_complaint"

_PROPOSAL_STATUS = sa.Enum(
    "pending_approval",
    "approved",
    "rejected",
    name=PROPOSAL_STATUS_ENUM,
    native_enum=False,
    create_constraint=True,
    length=30,
)
_PRIORITY = sa.Enum(
    "normal",
    "high",
    "urgent",
    name=PRIORITY_ENUM,
    native_enum=False,
    create_constraint=True,
    length=20,
)


def upgrade() -> None:
    op.create_table(
        "work_order_proposals",
        sa.Column("complaint_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            _PROPOSAL_STATUS,
            server_default="pending_approval",
            nullable=False,
        ),
        sa.Column(
            "context_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("problem_description", sa.Text(), nullable=False),
        sa.Column("proposed_scope", sa.Text(), nullable=False),
        sa.Column("technical_findings", sa.Text(), nullable=False),
        sa.Column(
            "recommended_actions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "required_skills",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "required_parts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("priority", _PRIORITY, nullable=False),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "safety_warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "missing_information",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "generation_warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("diagnostic_status", sa.String(length=40), nullable=False),
        sa.Column("diagnostic_summary", sa.Text(), nullable=False),
        sa.Column(
            "diagnostic_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "requires_escalation",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("escalation_reason", sa.Text(), nullable=True),
        sa.Column(
            "technician_recommendations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("selected_technician_id", sa.UUID(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("resulting_work_order_id", sa.UUID(), nullable=True),
        sa.Column("resulting_assignment_id", sa.UUID(), nullable=True),
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estimated_duration_minutes IS NULL "
            "OR estimated_duration_minutes >= 0",
            name=op.f(
                "ck_work_order_proposals_estimated_duration_non_negative"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["complaint_id"],
            ["complaints.id"],
            name=op.f(
                "fk_work_order_proposals_complaint_id_complaints"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["selected_technician_id"],
            ["technicians.id"],
            name=op.f(
                "fk_work_order_proposals_selected_technician_id_technicians"
            ),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_work_order_proposals_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["users.id"],
            name=op.f("fk_work_order_proposals_reviewed_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resulting_work_order_id"],
            ["work_orders.id"],
            name=op.f(
                "fk_work_order_proposals_resulting_work_order_id_work_orders"
            ),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resulting_assignment_id"],
            ["technician_assignments.id"],
            name=op.f(
                "fk_work_order_proposals_resulting_assignment_id_"
                "technician_assignments"
            ),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_work_order_proposals"),
        ),
        sa.UniqueConstraint(
            "resulting_work_order_id",
            name="uq_work_order_proposals_resulting_work_order_id",
        ),
        sa.UniqueConstraint(
            "resulting_assignment_id",
            name="uq_work_order_proposals_resulting_assignment_id",
        ),
    )
    op.create_index(
        "ix_work_order_proposals_complaint_id",
        "work_order_proposals",
        ["complaint_id"],
        unique=False,
    )
    op.create_index(
        "ix_work_order_proposals_status",
        "work_order_proposals",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_work_order_proposals_created_by_id",
        "work_order_proposals",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        PENDING_INDEX,
        "work_order_proposals",
        ["complaint_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending_approval'"),
    )


def downgrade() -> None:
    op.drop_index(
        PENDING_INDEX,
        table_name="work_order_proposals",
        postgresql_where=sa.text("status = 'pending_approval'"),
    )
    op.drop_index(
        "ix_work_order_proposals_created_by_id",
        table_name="work_order_proposals",
    )
    op.drop_index(
        "ix_work_order_proposals_status",
        table_name="work_order_proposals",
    )
    op.drop_index(
        "ix_work_order_proposals_complaint_id",
        table_name="work_order_proposals",
    )
    op.drop_table("work_order_proposals")
