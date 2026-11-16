from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.models.enums import ComplaintChannel, MessageSenderType

MESSAGE_CONTENT_MAX_LENGTH = 10000


class ConversationResponse(BaseModel):
    id: uuid.UUID
    complaint_id: uuid.UUID
    channel: ComplaintChannel
    created_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_type: MessageSenderType
    content: str
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    total: int
    limit: int
    offset: int


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(
        min_length=1,
        max_length=MESSAGE_CONTENT_MAX_LENGTH,
    )

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content may not be blank")
        if len(stripped) > MESSAGE_CONTENT_MAX_LENGTH:
            raise ValueError(
                "content must be at most "
                f"{MESSAGE_CONTENT_MAX_LENGTH} characters"
            )
        return stripped
