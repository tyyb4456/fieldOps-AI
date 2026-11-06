from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import ComplaintStatus, enum_type

if TYPE_CHECKING:
    from app.models.complaint import Complaint


class ComplaintHistory(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "complaint_history"
    __table_args__ = (
        UniqueConstraint(
            "complaint_id",
            "sequence_number",
            name="uq_complaint_history_complaint_sequence",
        ),
        Index("ix_complaint_history_complaint_id", "complaint_id"),
        Index("ix_complaint_history_created_at", "created_at"),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[ComplaintStatus | None] = mapped_column(
        enum_type(ComplaintStatus, "complaint_history_from_status"),
        nullable=True,
    )
    to_status: Mapped[ComplaintStatus | None] = mapped_column(
        enum_type(ComplaintStatus, "complaint_history_to_status"),
        nullable=True,
    )
    changed_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    complaint: Mapped[Complaint] = relationship(
        back_populates="history",
        foreign_keys=[complaint_id],
    )

    def __repr__(self) -> str:
        return (
            f"ComplaintHistory(id={self.id!r}, "
            f"event_type={self.event_type!r})"
        )
