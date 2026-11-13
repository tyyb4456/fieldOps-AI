from __future__ import annotations

import hashlib
import uuid
from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.background_task import BackgroundTask
from app.models.document import Document
from app.models.enums import (
    BackgroundTaskStatus,
    IngestionStatus,
    OutboxEventStatus,
)
from app.models.outbox_event import OutboxEvent
from app.services.documents import background
from app.services.tasks import outbox


def _document() -> Document:
    content = b"pdf"
    return Document(
        manufacturer="Acme Solar",
        model="INV-5000",
        document_name="INV-5000 Manual",
        version="1.0",
        storage_key=f"documents/{uuid.uuid4().hex}.pdf",
        original_filename="manual.pdf",
        content_type="application/pdf",
        byte_size=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )


async def _add_document(session: AsyncSession) -> Document:
    document = _document()
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


async def test_enqueue_creates_task_and_publishes_outbox(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = await _add_document(migrated_db_session)
    monkeypatch.setattr(settings, "celery_task_always_eager", False)

    published: list[tuple[str, list[str], str]] = []

    def fake_publish(event: OutboxEvent) -> None:
        published.append(
            (
                event.event_type,
                [str(event.payload["document_id"]), str(event.payload["background_task_id"])],
                str(event.payload["celery_task_id"]),
            )
        )

    monkeypatch.setattr(outbox, "_publish_outbox_event", fake_publish)

    returned = await background.enqueue_document_ingestion(
        migrated_db_session,
        document.id,
        storage=cast(Any, None),
        vector_index=cast(Any, None),
    )

    assert returned.ingestion_status is IngestionStatus.PENDING

    task = await migrated_db_session.scalar(
        select(BackgroundTask).where(
            BackgroundTask.resource_id == document.id,
        )
    )
    assert task is not None
    assert task.status is BackgroundTaskStatus.PENDING

    event = await migrated_db_session.scalar(
        select(OutboxEvent).where(OutboxEvent.event_type == task.task_name)
    )
    assert event is not None
    assert event.status is OutboxEventStatus.PUBLISHED
    assert event.published_at is not None
    assert event.attempts == 1
    assert published == [
        (
            task.task_name,
            [str(document.id), str(task.id)],
            str(task.celery_task_id),
        )
    ]


async def test_failed_publish_keeps_outbox_pending_without_failing_document(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = await _add_document(migrated_db_session)
    monkeypatch.setattr(settings, "celery_task_always_eager", False)

    def fail_publish(event: OutboxEvent) -> None:
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(outbox, "_publish_outbox_event", fail_publish)

    returned = await background.enqueue_document_ingestion(
        migrated_db_session,
        document.id,
        storage=cast(Any, None),
        vector_index=cast(Any, None),
    )

    assert returned.ingestion_status is IngestionStatus.PENDING

    task = await migrated_db_session.scalar(
        select(BackgroundTask).where(
            BackgroundTask.resource_id == document.id,
        )
    )
    assert task is not None
    assert task.status is BackgroundTaskStatus.PENDING

    event = await migrated_db_session.scalar(
        select(OutboxEvent).where(OutboxEvent.event_type == task.task_name)
    )
    assert event is not None
    assert event.status is OutboxEventStatus.PENDING
    assert event.attempts == 1
    assert event.last_error == "broker unavailable"


async def test_eager_mode_runs_inline_without_outbox(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = await _add_document(migrated_db_session)
    monkeypatch.setattr(settings, "celery_task_always_eager", True)

    inline_calls: list[uuid.UUID] = []

    async def fake_inline(
        session: AsyncSession,
        document_id: uuid.UUID,
        background_task_id: uuid.UUID,
        *,
        storage: object,
        vector_index: object,
    ) -> Document:
        inline_calls.append(document_id)
        return document

    monkeypatch.setattr(background, "_run_inline", fake_inline)

    returned = await background.enqueue_document_ingestion(
        migrated_db_session,
        document.id,
        storage=cast(Any, None),
        vector_index=cast(Any, None),
    )

    assert returned is document
    assert inline_calls == [document.id]
    assert (
        await migrated_db_session.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "documents.ingest_document")
        )
    ) is None
