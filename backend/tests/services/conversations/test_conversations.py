from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.conversation import Conversation
from app.models.enums import MessageSenderType
from app.models.message import Message
from app.services.conversations import conversations as conversation_service
from app.services.conversations.conversations import (
    MessageIdempotencyConflictError,
    is_message_idempotency_conflict,
)
from app.services.shared.authorization import AccessDeniedError
from tests.support import (
    seed_complaint,
    seed_conversation,
    seed_customer,
    seed_message,
)


async def test_service_replays_idempotent_message(
    committed_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(committed_db_session)
    complaint = await seed_complaint(committed_db_session, customer)
    conversation = await seed_conversation(committed_db_session, complaint)
    key = f"service-{uuid.uuid4().hex}"

    first, first_created = await conversation_service.create_message(
        committed_db_session,
        conversation=conversation,
        sender_type=MessageSenderType.CUSTOMER,
        content="Idempotent service message.",
        client_message_id=key,
    )
    replay, replay_created = await conversation_service.create_message(
        committed_db_session,
        conversation=conversation,
        sender_type=MessageSenderType.CUSTOMER,
        content="Idempotent service message.",
        client_message_id=key,
    )

    assert first_created is True
    assert replay_created is False
    assert replay.id == first.id

    with pytest.raises(MessageIdempotencyConflictError):
        await conversation_service.create_message(
            committed_db_session,
            conversation=conversation,
            sender_type=MessageSenderType.CUSTOMER,
            content="Different content.",
            client_message_id=key,
        )


async def test_service_lists_messages_chronologically(
    committed_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(committed_db_session)
    complaint = await seed_complaint(committed_db_session, customer)
    conversation = await seed_conversation(committed_db_session, complaint)
    base = datetime(2026, 1, 1, tzinfo=UTC)

    await seed_message(
        committed_db_session,
        conversation,
        content="Later",
        created_at=base + timedelta(hours=1),
    )
    await seed_message(
        committed_db_session,
        conversation,
        content="Earlier",
        created_at=base,
    )

    items, total = await conversation_service.list_messages(
        committed_db_session,
        conversation_id=conversation.id,
        limit=10,
        offset=0,
    )

    assert total == 2
    assert [message.content for message in items] == ["Earlier", "Later"]


async def test_service_rejects_foreign_customer_conversation(
    committed_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(committed_db_session)
    complaint = await seed_complaint(committed_db_session, customer)
    conversation = await seed_conversation(committed_db_session, complaint)
    _, other_customer, _ = await seed_customer(committed_db_session)

    with pytest.raises(AccessDeniedError):
        await conversation_service.get_conversation_for_customer(
            committed_db_session,
            customer_id=other_customer.id,
            conversation_id=conversation.id,
        )


def _session_factory(
    session: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
    assert session.bind is not None
    return async_sessionmaker(
        bind=session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def _wait_for_blocked_statement(
    session: AsyncSession,
    *,
    timeout: float = 20.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    snapshot: list[tuple[object, ...]] = []
    while asyncio.get_running_loop().time() < deadline:
        rows = (
            await session.execute(
                text(
                    "SELECT pid, state, wait_event_type, wait_event, query "
                    "FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND pid <> pg_backend_pid()"
                )
            )
        ).all()
        snapshot = [tuple(row) for row in rows]
        if any(
            row[2] == "Lock"
            and "INSERT INTO messages" in str(row[4])
            for row in rows
        ):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(
        f"timed out waiting for a blocked message insert: {snapshot}"
    )


async def _seed_conversation_id(
    session: AsyncSession,
) -> uuid.UUID:
    _, customer, _ = await seed_customer(session)
    complaint = await seed_complaint(session, customer)
    conversation = await seed_conversation(session, complaint)
    return conversation.id


async def test_postgres_concurrent_identical_submission_replays_committed(
    committed_db_session: AsyncSession,
) -> None:
    conversation_id = await _seed_conversation_id(committed_db_session)
    key = f"concurrent-{uuid.uuid4().hex}"
    factory = _session_factory(committed_db_session)

    async with factory() as winner:
        winner_conversation = await winner.get(
            Conversation,
            conversation_id,
        )
        assert winner_conversation is not None
        original, created = await conversation_service.create_message(
            winner,
            conversation=winner_conversation,
            sender_type=MessageSenderType.CUSTOMER,
            content="Concurrent identical message.",
            client_message_id=key,
        )
        assert created is True

        async with factory() as loser:
            loser_conversation = await loser.get(
                Conversation,
                conversation_id,
            )
            assert loser_conversation is not None

            async def insert_duplicate() -> tuple[Message, bool]:
                return await conversation_service.create_message(
                    loser,
                    conversation=loser_conversation,
                    sender_type=MessageSenderType.CUSTOMER,
                    content="Concurrent identical message.",
                    client_message_id=key,
                )

            blocked = asyncio.create_task(insert_duplicate())
            await _wait_for_blocked_statement(committed_db_session)
            assert not blocked.done()

            await winner.commit()

            with pytest.raises(IntegrityError) as excinfo:
                await asyncio.wait_for(blocked, timeout=10)
            assert is_message_idempotency_conflict(excinfo.value)

            await loser.rollback()
            replay = await conversation_service.resolve_idempotent_replay(
                loser,
                conversation_id=conversation_id,
                sender_type=MessageSenderType.CUSTOMER,
                content="Concurrent identical message.",
                client_message_id=key,
            )

    assert replay is not None
    assert replay.id == original.id

    async with factory() as probe:
        count = await probe.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.client_message_id == key)
        )
        assert count == 1


@pytest.mark.parametrize(
    ("loser_sender", "loser_content"),
    [
        (MessageSenderType.CUSTOMER, "Different concurrent content."),
        (MessageSenderType.STAFF, "Concurrent identical message."),
    ],
)
async def test_postgres_concurrent_conflicting_replay_reports_conflict(
    committed_db_session: AsyncSession,
    loser_sender: MessageSenderType,
    loser_content: str,
) -> None:
    conversation_id = await _seed_conversation_id(committed_db_session)
    key = f"concurrent-{uuid.uuid4().hex}"
    factory = _session_factory(committed_db_session)

    async with factory() as winner:
        winner_conversation = await winner.get(
            Conversation,
            conversation_id,
        )
        assert winner_conversation is not None
        await conversation_service.create_message(
            winner,
            conversation=winner_conversation,
            sender_type=MessageSenderType.CUSTOMER,
            content="Concurrent identical message.",
            client_message_id=key,
        )

        async with factory() as loser:
            loser_conversation = await loser.get(
                Conversation,
                conversation_id,
            )
            assert loser_conversation is not None

            async def insert_duplicate() -> tuple[Message, bool]:
                return await conversation_service.create_message(
                    loser,
                    conversation=loser_conversation,
                    sender_type=loser_sender,
                    content=loser_content,
                    client_message_id=key,
                )

            blocked = asyncio.create_task(insert_duplicate())
            await _wait_for_blocked_statement(committed_db_session)
            assert not blocked.done()

            await winner.commit()

            with pytest.raises(IntegrityError) as excinfo:
                await asyncio.wait_for(blocked, timeout=10)
            assert is_message_idempotency_conflict(excinfo.value)

            await loser.rollback()
            with pytest.raises(MessageIdempotencyConflictError):
                await conversation_service.resolve_idempotent_replay(
                    loser,
                    conversation_id=conversation_id,
                    sender_type=loser_sender,
                    content=loser_content,
                    client_message_id=key,
                )

    async with factory() as probe:
        count = await probe.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.client_message_id == key)
        )
        assert count == 1


async def test_service_breaks_message_timestamp_ties_by_id(
    committed_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(committed_db_session)
    complaint = await seed_complaint(committed_db_session, customer)
    conversation = await seed_conversation(committed_db_session, complaint)
    tied_at = datetime(2026, 1, 1, tzinfo=UTC)
    higher_id = uuid.UUID(int=2)
    lower_id = uuid.UUID(int=1)

    committed_db_session.add_all(
        [
            Message(
                id=higher_id,
                conversation_id=conversation.id,
                sender_type=MessageSenderType.CUSTOMER,
                content="Higher id",
                created_at=tied_at,
            ),
            Message(
                id=lower_id,
                conversation_id=conversation.id,
                sender_type=MessageSenderType.CUSTOMER,
                content="Lower id",
                created_at=tied_at,
            ),
        ]
    )
    await committed_db_session.commit()

    items, total = await conversation_service.list_messages(
        committed_db_session,
        conversation_id=conversation.id,
        limit=10,
        offset=0,
    )

    assert total == 2
    assert [message.id for message in items] == [lower_id, higher_id]
