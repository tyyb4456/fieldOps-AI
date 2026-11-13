from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import WebhookEventStatus, enum_type


class WebhookEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_event_id",
            name="uq_webhook_events_provider_external_event_id",
        ),
        CheckConstraint(
            "payload_sha256 IS NULL OR payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="payload_sha256_format",
        ),
        Index("ix_webhook_events_status", "status"),
        Index("ix_webhook_events_provider", "provider"),
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    payload_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    status: Mapped[WebhookEventStatus] = mapped_column(
        enum_type(WebhookEventStatus, "webhook_event_status", length=20),
        nullable=False,
        default=WebhookEventStatus.RECEIVED,
        server_default=WebhookEventStatus.RECEIVED.value,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"WebhookEvent(id={self.id!r}, provider={self.provider!r}, "
            f"external_event_id={self.external_event_id!r})"
        )
