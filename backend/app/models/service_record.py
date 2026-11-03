from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.equipment import Equipment
    from app.models.technician import Technician
    from app.models.work_order import WorkOrder


class ServiceRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "service_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["work_order_id", "equipment_id"],
            ["work_orders.id", "work_orders.equipment_id"],
            name="fk_service_records_work_order_equipment",
            ondelete="RESTRICT",
        ),
        Index("ix_service_records_equipment_id", "equipment_id"),
        Index("ix_service_records_work_order_id", "work_order_id"),
        Index("ix_service_records_technician_id", "technician_id"),
    )

    equipment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment.id", ondelete="RESTRICT"),
        nullable=False,
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    technician_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("technicians.id", ondelete="RESTRICT"),
        nullable=False,
    )
    findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_performed: Mapped[str | None] = mapped_column(Text, nullable=True)
    parts_used: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    equipment: Mapped[Equipment] = relationship(
        back_populates="service_records",
        foreign_keys=[equipment_id],
    )
    work_order: Mapped[WorkOrder] = relationship(
        back_populates="service_records",
        foreign_keys=[work_order_id],
    )
    technician: Mapped[Technician] = relationship(
        back_populates="service_records",
    )

    def __repr__(self) -> str:
        return f"ServiceRecord(id={self.id!r})"
