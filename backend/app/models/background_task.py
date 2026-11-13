from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import BackgroundTaskStatus, enum_type


class BackgroundTask(UUIDPrimaryKeyMixin, UpdatedAtMixin, Base):
    __tablename__ = "background_tasks"
    __table_args__ = (
        CheckConstraint(
            "attempts >= 0",
            name="attempts_non_negative",
        ),
        Index("ix_background_tasks_status", "status"),
        Index("ix_background_tasks_task_name", "task_name"),
        Index(
            "ix_background_tasks_resource",
            "resource_type",
            "resource_id",
        ),
    )

    task_name: Mapped[str] = mapped_column(String(150), nullable=False)
    celery_task_id: Mapped[str | None] = mapped_column(
        String(155),
        nullable=True,
        unique=True,
    )
    status: Mapped[BackgroundTaskStatus] = mapped_column(
        enum_type(BackgroundTaskStatus, "background_task_status", length=20),
        nullable=False,
        default=BackgroundTaskStatus.PENDING,
        server_default=BackgroundTaskStatus.PENDING.value,
    )
    resource_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"BackgroundTask(id={self.id!r}, task_name={self.task_name!r}, "
            f"status={self.status!r})"
        )
