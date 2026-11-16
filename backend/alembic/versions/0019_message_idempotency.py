"""add client message idempotency key

Revision ID: 0019_message_idempotency
Revises: 0018_workflow_proposal_run
Create Date: 2026-11-16 00:00:00.000000

Web and staff message submission accepts an ``Idempotency-Key`` header so a
retried request cannot create a second persisted message. The key is scoped to
one conversation. PostgreSQL unique constraints allow multiple NULL values, so
messages created without a key (for example provider-delivered messages) are
unaffected.

No backfill is required: existing rows keep ``client_message_id`` NULL and the
constraint is only enforced for new messages that supply a key.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_message_idempotency"
down_revision: str | None = "0018_workflow_proposal_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IDEMPOTENCY_CONSTRAINT = "uq_messages_conversation_client_message_id"


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("client_message_id", sa.String(length=128), nullable=True),
    )
    op.create_unique_constraint(
        IDEMPOTENCY_CONSTRAINT,
        "messages",
        ["conversation_id", "client_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        IDEMPOTENCY_CONSTRAINT,
        "messages",
        type_="unique",
    )
    op.drop_column("messages", "client_message_id")
