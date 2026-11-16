from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.enums import ComplaintChannel, MessageSenderType
from app.models.message import Message
from app.models.user import User
from app.services.complaints import complaints as complaint_service
from app.services.shared.authorization import (
    AccessDeniedError,
    is_admin,
    scope_conversations_for_customer,
    scope_conversations_for_user,
)

MESSAGE_IDEMPOTENCY_CONSTRAINT = (
    "uq_messages_conversation_client_message_id"
)


class MessageIdempotencyConflictError(Exception):
    """Raised when one idempotency key is reused for different content."""


def is_message_idempotency_conflict(exc: IntegrityError) -> bool:
    original = exc.orig
    sqlstate = getattr(original, "sqlstate", None) or getattr(
        original,
        "pgcode",
        None,
    )
    if sqlstate != "23505":
        return False

    constraint_name = getattr(original, "constraint_name", None)
    if constraint_name is None:
        diagnostic = getattr(original, "diag", None)
        constraint_name = getattr(diagnostic, "constraint_name", None)

    return (
        constraint_name == MESSAGE_IDEMPOTENCY_CONSTRAINT
        or MESSAGE_IDEMPOTENCY_CONSTRAINT in str(exc)
    )


async def create_conversation_for_complaint(
    session: AsyncSession,
    *,
    complaint_id: uuid.UUID,
    channel: ComplaintChannel,
    external_conversation_id: str | None = None,
) -> Conversation:
    conversation = Conversation(
        complaint_id=complaint_id,
        channel=channel,
        external_conversation_id=external_conversation_id,
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def list_conversations_for_customer(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
    complaint_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[Conversation], int]:
    if complaint_id is not None:
        # Resolve through the existing ownership-checked complaint query so a
        # missing or foreign complaint is indistinguishable from a 404.
        await complaint_service.get_complaint(
            session,
            complaint_id,
            customer_id=customer_id,
        )

    scoped = scope_conversations_for_customer(customer_id)
    if complaint_id is not None:
        scoped = scoped.where(Conversation.complaint_id == complaint_id)

    total = await session.scalar(
        select(func.count()).select_from(scoped.subquery())
    )
    result = await session.execute(
        scoped.order_by(
            Conversation.created_at.desc(),
            Conversation.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def list_conversations_for_staff(
    session: AsyncSession,
    user: User,
    *,
    complaint_id: uuid.UUID | None,
    channel: ComplaintChannel | None,
    limit: int,
    offset: int,
) -> tuple[list[Conversation], int]:
    if complaint_id is not None and is_admin(user):
        await complaint_service.get_complaint(session, complaint_id)

    scoped = scope_conversations_for_user(user)
    if complaint_id is not None:
        scoped = scoped.where(Conversation.complaint_id == complaint_id)
    if channel is not None:
        scoped = scoped.where(Conversation.channel == channel)

    total = await session.scalar(
        select(func.count()).select_from(scoped.subquery())
    )
    result = await session.execute(
        scoped.order_by(
            Conversation.created_at.desc(),
            Conversation.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_conversation_for_customer(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> Conversation:
    result = await session.execute(
        scope_conversations_for_customer(customer_id).where(
            Conversation.id == conversation_id
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise AccessDeniedError("Conversation not found")
    return conversation


async def get_conversation_for_staff(
    session: AsyncSession,
    user: User,
    conversation_id: uuid.UUID,
) -> Conversation:
    result = await session.execute(
        scope_conversations_for_user(user).where(
            Conversation.id == conversation_id
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise AccessDeniedError("Conversation not found")
    return conversation


async def list_messages(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    limit: int,
    offset: int,
) -> tuple[list[Message], int]:
    """Return messages ordered by ``created_at ASC, id ASC``.

    The UUID tie-break makes pagination deterministic when timestamps match,
    but it does not preserve exact insertion order for messages that share a
    timestamp: the database-generated ``created_at`` has no sequence number to
    disambiguate concurrent inserts.
    """

    total = await session.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.conversation_id == conversation_id)
    )
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_message_by_client_message_id(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    client_message_id: str,
) -> Message | None:
    result = await session.execute(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.client_message_id == client_message_id,
        )
    )
    return result.scalar_one_or_none()


def _verify_idempotent_replay(
    message: Message,
    *,
    sender_type: MessageSenderType,
    content: str,
) -> None:
    if message.sender_type is not sender_type or message.content != content:
        raise MessageIdempotencyConflictError(
            "Idempotency key was already used for different content"
        )


async def create_message(
    session: AsyncSession,
    *,
    conversation: Conversation,
    sender_type: MessageSenderType,
    content: str,
    client_message_id: str,
) -> tuple[Message, bool]:
    existing = await get_message_by_client_message_id(
        session,
        conversation_id=conversation.id,
        client_message_id=client_message_id,
    )
    if existing is not None:
        _verify_idempotent_replay(
            existing,
            sender_type=sender_type,
            content=content,
        )
        return existing, False

    message = Message(
        conversation_id=conversation.id,
        sender_type=sender_type,
        content=content,
        client_message_id=client_message_id,
    )
    session.add(message)
    await session.flush()
    return message, True


async def resolve_idempotent_replay(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    sender_type: MessageSenderType,
    content: str,
    client_message_id: str,
) -> Message | None:
    existing = await get_message_by_client_message_id(
        session,
        conversation_id=conversation_id,
        client_message_id=client_message_id,
    )
    if existing is None:
        return None
    _verify_idempotent_replay(
        existing,
        sender_type=sender_type,
        content=content,
    )
    return existing


__all__ = [
    "MessageIdempotencyConflictError",
    "create_conversation_for_complaint",
    "create_message",
    "get_conversation_for_customer",
    "get_conversation_for_staff",
    "get_message_by_client_message_id",
    "is_message_idempotency_conflict",
    "list_conversations_for_customer",
    "list_conversations_for_staff",
    "list_messages",
    "resolve_idempotent_replay",
]
