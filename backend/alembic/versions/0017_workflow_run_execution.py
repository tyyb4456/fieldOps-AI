"""add workflow-run execution metadata

Revision ID: 0017_workflow_run_execution
Revises: 0016_outbox_events
Create Date: 2026-11-13 00:00:00.000000

Step 4.9 moves long-running diagnostic and work-order-preparation workflows
out of FastAPI request handling. A ``workflow_runs`` row is created with the
background task and outbox event in one transaction. The row records the
workflow type, the requesting operator, the persisted input and the final
result payload so status reads never depend on Celery's result backend.

Existing workflow runs created by the admin lifecycle endpoints remain valid:
the new columns are nullable (or have an empty-object default) so legacy rows
do not need a destructive backfill.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017_workflow_run_execution"
down_revision: str | None = "0016_outbox_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKFLOW_RUN_TYPE_ENUM = "workflow_run_type"

_WORKFLOW_RUN_TYPE = sa.Enum(
    "diagnostic_investigation",
    "work_order_proposal",
    name=WORKFLOW_RUN_TYPE_ENUM,
    native_enum=False,
    create_constraint=True,
    length=40,
)


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column("workflow_type", _WORKFLOW_RUN_TYPE, nullable=True),
    )
    op.add_column(
        "workflow_runs",
        sa.Column("requested_by_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "workflow_runs",
        sa.Column(
            "input_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "workflow_runs",
        sa.Column(
            "result_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        op.f("fk_workflow_runs_requested_by_id_users"),
        "workflow_runs",
        "users",
        ["requested_by_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_workflow_runs_workflow_type",
        "workflow_runs",
        ["workflow_type"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_runs_requested_by_id",
        "workflow_runs",
        ["requested_by_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workflow_runs_requested_by_id",
        table_name="workflow_runs",
    )
    op.drop_index(
        "ix_workflow_runs_workflow_type",
        table_name="workflow_runs",
    )
    op.drop_constraint(
        op.f("fk_workflow_runs_requested_by_id_users"),
        "workflow_runs",
        type_="foreignkey",
    )
    op.drop_column("workflow_runs", "result_payload")
    op.drop_column("workflow_runs", "input_payload")
    op.drop_column("workflow_runs", "requested_by_id")
    op.drop_column("workflow_runs", "workflow_type")
