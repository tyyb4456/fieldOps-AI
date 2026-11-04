from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.complaint import Complaint
    from app.models.equipment import Equipment
    from app.models.user import User


class Customer(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "customers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    user: Mapped[User] = relationship(back_populates="customer")
    equipment: Mapped[list[Equipment]] = relationship(
        back_populates="customer",
        passive_deletes="all",
    )
    complaints: Mapped[list[Complaint]] = relationship(
        back_populates="customer",
        foreign_keys="Complaint.customer_id",
        passive_deletes="all",
    )

    def __repr__(self) -> str:
        return f"Customer(id={self.id!r}, user_id={self.user_id!r})"
