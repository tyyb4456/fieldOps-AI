from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.complaint import Complaint
    from app.models.customer import Customer
    from app.models.service_record import ServiceRecord
    from app.models.work_order import WorkOrder


class Equipment(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "equipment"
    __table_args__ = (
        UniqueConstraint(
            "manufacturer",
            "serial_number",
            name="uq_equipment_manufacturer_serial_number",
        ),
        UniqueConstraint(
            "id",
            "customer_id",
            name="uq_equipment_id_customer_id",
        ),
        Index("ix_equipment_customer_id", "customer_id"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    manufacturer: Mapped[str] = mapped_column(String(150), nullable=False)
    model: Mapped[str] = mapped_column(String(150), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )
    equipment_type: Mapped[str] = mapped_column(String(80), nullable=False)
    installation_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    customer: Mapped[Customer] = relationship(back_populates="equipment")
    complaints: Mapped[list[Complaint]] = relationship(
        back_populates="equipment",
        foreign_keys="Complaint.equipment_id",
        passive_deletes="all",
    )
    work_orders: Mapped[list[WorkOrder]] = relationship(
        back_populates="equipment",
        foreign_keys="WorkOrder.equipment_id",
        passive_deletes="all",
    )
    service_records: Mapped[list[ServiceRecord]] = relationship(
        back_populates="equipment",
        foreign_keys="ServiceRecord.equipment_id",
        passive_deletes="all",
    )

    def __repr__(self) -> str:
        return f"Equipment(id={self.id!r}, model={self.model!r})"
