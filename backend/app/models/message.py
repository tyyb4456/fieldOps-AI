from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import MediaType, MessageSenderType, enum_type

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class Message(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sender_type: Mapped[MessageSenderType] = mapped_column(
        enum_type(MessageSenderType, "message_sender_type", length=20),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    media_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_type: Mapped[MediaType | None] = mapped_column(
        enum_type(MediaType, "message_media_type", length=20),
        nullable=True,
    )
    external_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )

    conversation: Mapped[Conversation] = relationship(
        back_populates="messages",
    )

    def __repr__(self) -> str:
        return f"Message(id={self.id!r}, sender_type={self.sender_type!r})"
