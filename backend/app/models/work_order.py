from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import Priority, WorkOrderStatus, enum_type

if TYPE_CHECKING:
    from app.models.complaint import Complaint
    from app.models.completion_report import CompletionReport
    from app.models.equipment import Equipment
    from app.models.service_record import ServiceRecord
    from app.models.technician_assignment import TechnicianAssignment


class WorkOrder(UUIDPrimaryKeyMixin, UpdatedAtMixin, Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["complaint_id", "equipment_id"],
            ["complaints.id", "complaints.equipment_id"],
            name="fk_work_orders_complaint_equipment",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "complaint_id",
            name="uq_work_orders_complaint_id",
        ),
        UniqueConstraint(
            "id",
            "equipment_id",
            name="uq_work_orders_id_equipment_id",
        ),
        Index("ix_work_orders_equipment_id", "equipment_id"),
        Index("ix_work_orders_status", "status"),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="RESTRICT"),
        nullable=False,
    )
    equipment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    diagnostic_checklist: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    priority: Mapped[Priority] = mapped_column(
        enum_type(Priority, "work_order_priority", length=20),
        nullable=False,
        default=Priority.NORMAL,
        server_default=Priority.NORMAL.value,
    )
    status: Mapped[WorkOrderStatus] = mapped_column(
        enum_type(WorkOrderStatus, "work_order_status"),
        nullable=False,
        default=WorkOrderStatus.DRAFT,
        server_default=WorkOrderStatus.DRAFT.value,
    )

    complaint: Mapped[Complaint] = relationship(
        back_populates="work_order",
        foreign_keys=[complaint_id],
    )
    equipment: Mapped[Equipment] = relationship(
        back_populates="work_orders",
        foreign_keys=[equipment_id],
    )
    assignments: Mapped[list[TechnicianAssignment]] = relationship(
        back_populates="work_order",
    )
    service_records: Mapped[list[ServiceRecord]] = relationship(
        back_populates="work_order",
        foreign_keys="ServiceRecord.work_order_id",
    )
    completion_reports: Mapped[list[CompletionReport]] = relationship(
        back_populates="work_order",
    )

    def __repr__(self) -> str:
        return f"WorkOrder(id={self.id!r}, status={self.status!r})"
