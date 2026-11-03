from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import ComplaintChannel, enum_type

if TYPE_CHECKING:
    from app.models.complaint import Complaint
    from app.models.message import Message


class Conversation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint(
            "external_conversation_id",
            name="uq_conversations_external_conversation_id",
        ),
        Index("ix_conversations_complaint_id", "complaint_id"),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="RESTRICT"),
        nullable=False,
    )
    channel: Mapped[ComplaintChannel] = mapped_column(
        enum_type(ComplaintChannel, "conversation_channel", length=20),
        nullable=False,
    )
    external_conversation_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    complaint: Mapped[Complaint] = relationship(
        back_populates="conversations",
    )
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
    )

    def __repr__(self) -> str:
        return f"Conversation(id={self.id!r}, channel={self.channel!r})"
