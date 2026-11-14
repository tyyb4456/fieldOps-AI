"""add originating workflow run to work-order proposals

Revision ID: 0018_workflow_proposal_run
Revises: 0017_workflow_run_execution
Create Date: 2026-11-14 00:00:00.000000

A redelivered workflow job must be able to recognize a proposal that its own
WorkflowRun already persisted before the worker crashed. The nullable
``source_workflow_run_id`` column ties a proposal to that run. The unique
constraint allows many NULL values (synchronous service proposals) while
guaranteeing at most one proposal per workflow run at the database level.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_workflow_proposal_run"
down_revision: str | None = "0017_workflow_run_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "work_order_proposals",
        sa.Column("source_workflow_run_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_work_order_proposals_source_workflow_run_id_workflow_runs"),
        "work_order_proposals",
        "workflow_runs",
        ["source_workflow_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        op.f("uq_work_order_proposals_source_workflow_run_id"),
        "work_order_proposals",
        ["source_workflow_run_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_work_order_proposals_source_workflow_run_id"),
        "work_order_proposals",
        type_="unique",
    )
    op.drop_constraint(
        op.f("fk_work_order_proposals_source_workflow_run_id_workflow_runs"),
        "work_order_proposals",
        type_="foreignkey",
    )
    op.drop_column("work_order_proposals", "source_workflow_run_id")
