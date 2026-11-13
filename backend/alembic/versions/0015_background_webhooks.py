"""add background task tracking and webhook idempotency

Revision ID: 0015_background_webhooks
Revises: 0014_work_order_proposals
Create Date: 2026-11-12 00:00:00.000000

Step 4.8 introduces Redis and Celery for durable background execution.
``background_tasks`` is an operational record for queued and executed Celery
jobs; it deliberately has no complaint foreign key so non-workflow jobs can be
tracked without overloading ``workflow_runs``.

``webhook_events`` stores the provider event identity with a unique constraint
so retried deliveries are acknowledged without repeating side effects. No
provider endpoint is wired in this step; the service is ready for the WhatsApp
integration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015_background_webhooks"
down_revision: str | None = "0014_work_order_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BACKGROUND_TASK_STATUS_ENUM = "background_task_status"
WEBHOOK_EVENT_STATUS_ENUM = "webhook_event_status"

_BACKGROUND_TASK_STATUS = sa.Enum(
    "pending",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    name=BACKGROUND_TASK_STATUS_ENUM,
    native_enum=False,
    create_constraint=True,
    length=20,
)
_WEBHOOK_EVENT_STATUS = sa.Enum(
    "received",
    "processed",
    "failed",
    "ignored",
    name=WEBHOOK_EVENT_STATUS_ENUM,
    native_enum=False,
    create_constraint=True,
    length=20,
)


def upgrade() -> None:
    op.create_table(
        "background_tasks",
        sa.Column("task_name", sa.String(length=150), nullable=False),
        sa.Column("celery_task_id", sa.String(length=155), nullable=True),
        sa.Column(
            "status",
            _BACKGROUND_TASK_STATUS,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(length=50), nullable=True),
        sa.Column("resource_id", sa.UUID(), nullable=True),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
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
            "attempts >= 0",
            name=op.f("ck_background_tasks_attempts_non_negative"),
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_background_tasks"),
        ),
        sa.UniqueConstraint(
            "celery_task_id",
            name=op.f("uq_background_tasks_celery_task_id"),
        ),
    )
    op.create_index(
        "ix_background_tasks_status",
        "background_tasks",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_background_tasks_task_name",
        "background_tasks",
        ["task_name"],
        unique=False,
    )
    op.create_index(
        "ix_background_tasks_resource",
        "background_tasks",
        ["resource_type", "resource_id"],
        unique=False,
    )

    op.create_table(
        "webhook_events",
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column(
            "external_event_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=100), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            _WEBHOOK_EVENT_STATUS,
            server_default="received",
            nullable=False,
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "payload_sha256 IS NULL OR payload_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_webhook_events_payload_sha256_format"),
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_webhook_events"),
        ),
        sa.UniqueConstraint(
            "provider",
            "external_event_id",
            name="uq_webhook_events_provider_external_event_id",
        ),
    )
    op.create_index(
        "ix_webhook_events_status",
        "webhook_events",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_events_provider",
        "webhook_events",
        ["provider"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_webhook_events_provider",
        table_name="webhook_events",
    )
    op.drop_index(
        "ix_webhook_events_status",
        table_name="webhook_events",
    )
    op.drop_table("webhook_events")

    op.drop_index(
        "ix_background_tasks_resource",
        table_name="background_tasks",
    )
    op.drop_index(
        "ix_background_tasks_task_name",
        table_name="background_tasks",
    )
    op.drop_index(
        "ix_background_tasks_status",
        table_name="background_tasks",
    )
    op.drop_table("background_tasks")
