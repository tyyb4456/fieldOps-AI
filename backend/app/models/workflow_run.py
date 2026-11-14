from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import WorkflowRunStatus, WorkflowRunType, enum_type

if TYPE_CHECKING:
    from app.models.complaint import Complaint


class WorkflowRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("ix_workflow_runs_complaint_id", "complaint_id"),
        Index("ix_workflow_runs_status", "status"),
        Index("ix_workflow_runs_workflow_type", "workflow_type"),
        Index("ix_workflow_runs_requested_by_id", "requested_by_id"),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workflow_type: Mapped[WorkflowRunType | None] = mapped_column(
        enum_type(WorkflowRunType, "workflow_run_type", length=40),
        nullable=True,
    )
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    input_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    status: Mapped[WorkflowRunStatus] = mapped_column(
        enum_type(WorkflowRunStatus, "workflow_run_status", length=20),
        nullable=False,
        default=WorkflowRunStatus.RUNNING,
        server_default=WorkflowRunStatus.RUNNING.value,
    )
    current_step: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    complaint: Mapped[Complaint] = relationship(
        back_populates="workflow_runs",
    )

    def __repr__(self) -> str:
        return f"WorkflowRun(id={self.id!r}, status={self.status!r})"
