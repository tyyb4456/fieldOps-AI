from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import AssignmentStatus, enum_type

if TYPE_CHECKING:
    from app.models.technician import Technician
    from app.models.work_order import WorkOrder


class TechnicianAssignment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "technician_assignments"
    __table_args__ = (
        Index(
            "ix_technician_assignments_work_order_id",
            "work_order_id",
        ),
        Index(
            "ix_technician_assignments_technician_id",
            "technician_id",
        ),
    )

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    technician_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("technicians.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    assignment_status: Mapped[AssignmentStatus] = mapped_column(
        enum_type(
            AssignmentStatus,
            "technician_assignment_status",
            length=30,
        ),
        nullable=False,
        default=AssignmentStatus.OFFERED,
        server_default=AssignmentStatus.OFFERED.value,
    )

    work_order: Mapped[WorkOrder] = relationship(
        back_populates="assignments",
    )
    technician: Mapped[Technician] = relationship(
        back_populates="assignments",
    )

    def __repr__(self) -> str:
        return (
            "TechnicianAssignment("
            f"id={self.id!r}, "
            f"status={self.assignment_status!r})"
        )
