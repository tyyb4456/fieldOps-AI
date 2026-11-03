from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import EvidenceStatus, enum_type

if TYPE_CHECKING:
    from app.models.work_order import WorkOrder


class CompletionReport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "completion_reports"
    __table_args__ = (
        Index(
            "ix_completion_reports_work_order_id",
            "work_order_id",
        ),
    )

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_status: Mapped[EvidenceStatus] = mapped_column(
        enum_type(
            EvidenceStatus,
            "completion_report_evidence_status",
            length=20,
        ),
        nullable=False,
        default=EvidenceStatus.PENDING,
        server_default=EvidenceStatus.PENDING.value,
    )
    verification_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    work_order: Mapped[WorkOrder] = relationship(
        back_populates="completion_reports",
    )

    def __repr__(self) -> str:
        return f"CompletionReport(id={self.id!r})"
