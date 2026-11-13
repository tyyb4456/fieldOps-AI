"""add transactional outbox events

Revision ID: 0016_outbox_events
Revises: 0015_background_webhooks
Create Date: 2026-11-13 00:00:00.000000

Step 4.8.1 introduces a PostgreSQL-backed transactional outbox. Document,
background-task and outbox rows are committed in one transaction; a dispatcher
publishes pending events to the existing Redis/Celery broker and marks them
published only after the broker accepts the message.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016_outbox_events"
down_revision: str | None = "0015_background_webhooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OUTBOX_EVENT_STATUS_ENUM = "outbox_event_status"

_OUTBOX_EVENT_STATUS = sa.Enum(
    "pending",
    "published",
    "failed",
    name=OUTBOX_EVENT_STATUS_ENUM,
    native_enum=False,
    create_constraint=True,
    length=20,
)


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("event_type", sa.String(length=150), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status",
            _OUTBOX_EVENT_STATUS,
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "published_at",
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
            name=op.f("ck_outbox_events_attempts_non_negative"),
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_outbox_events"),
        ),
    )
    op.create_index(
        "ix_outbox_events_status",
        "outbox_events",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_events_status_created_at",
        "outbox_events",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbox_events_status_created_at",
        table_name="outbox_events",
    )
    op.drop_index(
        "ix_outbox_events_status",
        table_name="outbox_events",
    )
    op.drop_table("outbox_events")
