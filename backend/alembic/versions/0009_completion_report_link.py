"""link completion reports to service records

Revision ID: 0009_completion_report_link
Revises: 0008_active_assignment_unique
Create Date: 2026-11-08 09:00:00.000000

A completion report describes the outcome of a work order and, when a service
record exists, must reference the record recorded against the same work order.
Enforce that association with a composite foreign key into the unique
``(service_records.id, service_records.work_order_id)`` pair, and guarantee a
single completion report per work order.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0009_completion_report_link"
down_revision: str | None = "0008_active_assignment_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SERVICE_RECORD_UNIQUE = "uq_service_records_id_work_order_id"
COMPLETION_REPORT_UNIQUE = "uq_completion_reports_work_order_id"
COMPLETION_REPORT_FK = "fk_completion_reports_service_record_work_order"
LEGACY_REPORT_INDEX = "ix_completion_reports_work_order_id"

_DUPLICATE_REPORTS_SQL = """
SELECT work_order_id, count(*) AS report_count
FROM completion_reports
GROUP BY work_order_id
HAVING count(*) > 1
LIMIT 1
"""


def upgrade() -> None:
    connection = op.get_bind()
    duplicate = connection.execute(
        sa.text(_DUPLICATE_REPORTS_SQL)
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot enforce one completion report per work order: "
            f"work_order_id {duplicate.work_order_id} has "
            f"{duplicate.report_count} completion reports. Remove the extra "
            "reports, then rerun the migration."
        )

    op.create_unique_constraint(
        SERVICE_RECORD_UNIQUE,
        "service_records",
        ["id", "work_order_id"],
    )
    op.drop_index(LEGACY_REPORT_INDEX, table_name="completion_reports")
    op.add_column(
        "completion_reports",
        sa.Column("service_record_id", sa.UUID(), nullable=True),
    )
    op.create_unique_constraint(
        COMPLETION_REPORT_UNIQUE,
        "completion_reports",
        ["work_order_id"],
    )
    op.create_foreign_key(
        COMPLETION_REPORT_FK,
        "completion_reports",
        "service_records",
        ["service_record_id", "work_order_id"],
        ["id", "work_order_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        COMPLETION_REPORT_FK,
        "completion_reports",
        type_="foreignkey",
    )
    op.drop_constraint(
        COMPLETION_REPORT_UNIQUE,
        "completion_reports",
        type_="unique",
    )
    op.drop_column("completion_reports", "service_record_id")
    op.create_index(
        LEGACY_REPORT_INDEX,
        "completion_reports",
        ["work_order_id"],
        unique=False,
    )
    op.drop_constraint(
        SERVICE_RECORD_UNIQUE,
        "service_records",
        type_="unique",
    )
