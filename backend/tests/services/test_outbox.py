from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.enums import OutboxEventStatus
from app.models.outbox_event import OutboxEvent
from app.services.tasks import outbox


def _event() -> OutboxEvent:
    document_id = uuid.uuid4()
    task_id = uuid.uuid4()
    return outbox.create_outbox_event(
        event_type="documents.ingest_document",
        payload={
            "document_id": str(document_id),
            "background_task_id": str(task_id),
            "celery_task_id": str(uuid.uuid4()),
        },
    )


async def test_dispatch_pending_publishes_and_marks_published(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _event()
    second = _event()
    migrated_db_session.add_all([first, second])
    await migrated_db_session.commit()

    published: list[uuid.UUID] = []
    monkeypatch.setattr(
        outbox,
        "_publish_outbox_event",
        lambda event: published.append(event.id),
    )

    result = await outbox.dispatch_pending_outbox_events(migrated_db_session)

    assert result.published == 2
    assert result.failed == 0
    assert result.pending == 0
    assert set(published) == {first.id, second.id}

    for event in (first, second):
        await migrated_db_session.refresh(event)
        assert event.status is OutboxEventStatus.PUBLISHED
        assert event.published_at is not None
        assert event.attempts == 1
        assert event.last_error is None


async def test_dispatch_retries_until_attempt_limit_then_fails(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "celery_outbox_max_publish_attempts", 2)
    event = _event()
    migrated_db_session.add(event)
    await migrated_db_session.commit()

    def fail_publish(candidate: OutboxEvent) -> None:
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(outbox, "_publish_outbox_event", fail_publish)

    first_result = await outbox.dispatch_pending_outbox_events(migrated_db_session)
    assert first_result.published == 0
    assert first_result.failed == 0
    assert first_result.pending == 1

    await migrated_db_session.refresh(event)
    assert event.status is OutboxEventStatus.PENDING
    assert event.attempts == 1
    assert event.last_error == "broker unavailable"

    second_result = await outbox.dispatch_pending_outbox_events(migrated_db_session)
    assert second_result.published == 0
    assert second_result.failed == 1
    assert second_result.pending == 0

    await migrated_db_session.refresh(event)
    assert event.status is OutboxEventStatus.FAILED
    assert event.attempts == 2


async def test_dispatch_single_event_is_idempotent_for_published_events(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = _event()
    migrated_db_session.add(event)
    await migrated_db_session.commit()

    calls: list[uuid.UUID] = []
    monkeypatch.setattr(
        outbox,
        "_publish_outbox_event",
        lambda candidate: calls.append(candidate.id),
    )

    assert await outbox.dispatch_outbox_event(migrated_db_session, event.id)
    assert not await outbox.dispatch_outbox_event(migrated_db_session, event.id)
    assert calls == [event.id]

    await migrated_db_session.refresh(event)
    assert event.status is OutboxEventStatus.PUBLISHED


async def test_concurrent_dispatchers_skip_locked_events(
    committed_migration_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(
        committed_migration_database.url,
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    try:
        async with session_factory() as setup:
            first = _event()
            second = _event()
            setup.add_all([first, second])
            await setup.commit()
            first_id = first.id
            second_id = second.id

        published: list[uuid.UUID] = []
        monkeypatch.setattr(
            outbox,
            "_publish_outbox_event",
            lambda candidate: published.append(candidate.id),
        )

        async with (
            session_factory() as holder,
            session_factory() as dispatcher,
        ):
            await holder.execute(
                select(OutboxEvent)
                .where(OutboxEvent.id == first_id)
                .with_for_update()
            )

            first_result = await outbox.dispatch_pending_outbox_events(
                dispatcher
            )

            assert published == [second_id]
            assert first_result.published == 1
            assert first_result.pending == 1

            await holder.rollback()

            second_result = await outbox.dispatch_pending_outbox_events(
                dispatcher
            )

            assert set(published) == {first_id, second_id}
            assert second_result.published == 1
            assert second_result.pending == 0
    finally:
        await engine.dispose()
