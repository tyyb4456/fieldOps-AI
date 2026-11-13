from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import OutboxEventStatus, enum_type


class OutboxEvent(UUIDPrimaryKeyMixin, UpdatedAtMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint(
            "attempts >= 0",
            name="attempts_non_negative",
        ),
        Index("ix_outbox_events_status", "status"),
        Index("ix_outbox_events_status_created_at", "status", "created_at"),
    )

    event_type: Mapped[str] = mapped_column(String(150), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[OutboxEventStatus] = mapped_column(
        enum_type(OutboxEventStatus, "outbox_event_status", length=20),
        nullable=False,
        default=OutboxEventStatus.PENDING,
        server_default=OutboxEventStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"OutboxEvent(id={self.id!r}, event_type={self.event_type!r}, "
            f"status={self.status!r})"
        )
