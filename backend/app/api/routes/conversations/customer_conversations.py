from __future__ import annotations

import logging
import uuid

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Query,
    Response,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    get_current_customer,
    require_customer_user,
)
from app.api.serializers import conversation_response, message_response
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.customer import Customer
from app.models.enums import ComplaintChannel, MessageSenderType
from app.models.user import User
from app.schemas.conversations.conversation import (
    ConversationListResponse,
    MessageCreate,
    MessageListResponse,
    MessageResponse,
)
from app.services.conversations import conversations as conversation_service
from app.services.conversations.conversations import (
    MessageIdempotencyConflictError,
    is_message_idempotency_conflict,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/customers/me",
    tags=["Customer Conversations"],
)

IDEMPOTENCY_KEY_HEADER = Header(
    alias="Idempotency-Key",
    min_length=1,
    max_length=128,
    pattern=r"^[A-Za-z0-9._:-]+$",
)


def _idempotency_conflict_error() -> AppError:
    return AppError(
        "Idempotency key was already used for a different message.",
        status_code=status.HTTP_409_CONFLICT,
        code="idempotency_conflict",
    )


def _unsupported_channel_error() -> AppError:
    # External delivery is not implemented, so accepting a customer message on
    # a non-web conversation would imply delivery that never happens.
    return AppError(
        "Customer messages are only supported on web conversations.",
        status_code=status.HTTP_409_CONFLICT,
        code="unsupported_conversation_channel",
    )


@router.get(
    "/complaints/{complaint_id}/conversations",
    response_model=ConversationListResponse,
    summary="List the authenticated customer's complaint conversations",
)
async def list_own_complaint_conversations(
    complaint_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationListResponse:
    items, total = await conversation_service.list_conversations_for_customer(
        session,
        customer_id=customer.id,
        complaint_id=complaint_id,
        limit=limit,
        offset=offset,
    )
    return ConversationListResponse(
        items=[conversation_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="List messages in one of the customer's conversations",
)
async def list_own_conversation_messages(
    conversation_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> MessageListResponse:
    await conversation_service.get_conversation_for_customer(
        session,
        customer_id=customer.id,
        conversation_id=conversation_id,
    )
    items, total = await conversation_service.list_messages(
        session,
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
    )
    return MessageListResponse(
        items=[message_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append a customer message to a conversation",
)
async def create_own_conversation_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    response: Response,
    idempotency_key: str = IDEMPOTENCY_KEY_HEADER,
    current_user: User = Depends(require_customer_user),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    conversation = await conversation_service.get_conversation_for_customer(
        session,
        customer_id=customer.id,
        conversation_id=conversation_id,
    )
    if conversation.channel is not ComplaintChannel.WEB:
        raise _unsupported_channel_error()
    try:
        message, created = await conversation_service.create_message(
            session,
            conversation=conversation,
            sender_type=MessageSenderType.CUSTOMER,
            content=payload.content,
            client_message_id=idempotency_key,
        )
        await session.commit()
    except MessageIdempotencyConflictError as exc:
        await session.rollback()
        raise _idempotency_conflict_error() from exc
    except IntegrityError as exc:
        await session.rollback()
        if not is_message_idempotency_conflict(exc):
            raise
        try:
            replay = (
                await conversation_service.resolve_idempotent_replay(
                    session,
                    conversation_id=conversation_id,
                    sender_type=MessageSenderType.CUSTOMER,
                    content=payload.content,
                    client_message_id=idempotency_key,
                )
            )
        except MessageIdempotencyConflictError as conflict_exc:
            raise _idempotency_conflict_error() from conflict_exc
        if replay is None:
            raise _idempotency_conflict_error() from exc
        message = replay
        created = False

    if not created:
        response.status_code = status.HTTP_200_OK
    else:
        await session.refresh(message)
        logger.info(
            "Customer message created",
            extra={
                "event": "customer_message_created",
                "actor_id": str(current_user.id),
                "customer_id": str(customer.id),
                "complaint_id": str(conversation.complaint_id),
                "conversation_id": str(conversation.id),
                "message_id": str(message.id),
            },
        )
    return message_response(message)
