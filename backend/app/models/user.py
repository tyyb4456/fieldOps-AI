from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, Text, text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole, enum_type

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.technician import Technician


class User(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )
    phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        unique=True,
    )
    clerk_user_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )
    password_hash: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    role: Mapped[UserRole] = mapped_column(
        enum_type(UserRole, "user_role", length=20),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    profile_enrichment_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    profile_enrichment_last_attempt_at: Mapped[datetime | None] = (
        mapped_column(DateTime(timezone=True), nullable=True)
    )
    profile_enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    customer: Mapped[Customer | None] = relationship(
        back_populates="user",
        uselist=False,
        passive_deletes="all",
    )
    technician: Mapped[Technician | None] = relationship(
        back_populates="user",
        uselist=False,
        passive_deletes="all",
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, role={self.role!r})"
