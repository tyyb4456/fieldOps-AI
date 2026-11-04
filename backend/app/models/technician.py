from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, Text, true, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.service_record import ServiceRecord
    from app.models.technician_assignment import TechnicianAssignment
    from app.models.user import User


class Technician(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "technicians"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    skills: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    service_area: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_available: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    user: Mapped[User] = relationship(back_populates="technician")
    assignments: Mapped[list[TechnicianAssignment]] = relationship(
        back_populates="technician",
        passive_deletes="all",
    )
    service_records: Mapped[list[ServiceRecord]] = relationship(
        back_populates="technician",
        passive_deletes="all",
    )

    def __repr__(self) -> str:
        return f"Technician(id={self.id!r}, user_id={self.user_id!r})"
