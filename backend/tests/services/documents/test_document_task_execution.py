from __future__ import annotations

import uuid
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.models.background_task import BackgroundTask
from app.models.document import Document
from app.models.enums import BackgroundTaskStatus, IngestionStatus
from app.services.documents.document_ingestion import (
    INGESTION_ERROR_EMBEDDING,
    TransientIngestionError,
)
from app.services.tasks.execution import (
    DOCUMENT_INGESTION_TASK_NAME,
    create_background_task,
)
from app.tasks import documents as document_tasks
from app.tasks.documents import (
    INGESTION_TASK_FAILED,
    _finalize_failed_task,
    run_document_ingestion,
)


def _document(*, status: IngestionStatus) -> Document:
    return Document(
        manufacturer="Acme Solar",
        model="INV-5000",
        document_name=f"Manual {uuid.uuid4().hex}",
        version="1.0",
        storage_key=f"documents/{uuid.uuid4().hex}.pdf",
        ingestion_status=status,
    )


def _task(
    document: Document,
    *,
    status: BackgroundTaskStatus,
) -> BackgroundTask:
    task = create_background_task(
        task_name=DOCUMENT_INGESTION_TASK_NAME,
        celery_task_id=str(uuid.uuid4()),
        resource_type="document",
        resource_id=document.id,
    )
    task.status = status
    return task


def _session_factory(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=cast(AsyncEngine, session.bind),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def test_duplicate_delivery_skips_succeeded_background_task(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document(status=IngestionStatus.READY)
    migrated_db_session.add(document)
    await migrated_db_session.flush()
    task = _task(document, status=BackgroundTaskStatus.SUCCEEDED)
    migrated_db_session.add(task)
    await migrated_db_session.commit()

    monkeypatch.setattr(
        document_tasks,
        "async_session_factory",
        _session_factory(migrated_db_session),
    )

    async def unexpected_ingestion(*args: object, **kwargs: object) -> Document:
        raise AssertionError("A succeeded task must not run ingestion again.")

    monkeypatch.setattr(
        document_tasks,
        "ingest_document",
        unexpected_ingestion,
    )

    result = await run_document_ingestion(document.id, task.id)

    assert result == str(document.id)
    await migrated_db_session.refresh(task)
    assert task.status is BackgroundTaskStatus.SUCCEEDED
    assert task.attempts == 0


async def test_duplicate_delivery_retries_failed_background_task(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document(status=IngestionStatus.FAILED)
    migrated_db_session.add(document)
    await migrated_db_session.flush()
    task = _task(document, status=BackgroundTaskStatus.FAILED)
    migrated_db_session.add(task)
    await migrated_db_session.commit()

    monkeypatch.setattr(
        document_tasks,
        "async_session_factory",
        _session_factory(migrated_db_session),
    )
    monkeypatch.setattr(
        document_tasks,
        "build_document_storage",
        lambda settings: object(),
    )
    monkeypatch.setattr(
        document_tasks,
        "get_embedding_provider",
        lambda: object(),
    )

    class FakeVectorIndex:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def close(self) -> None:
            return None

    monkeypatch.setattr(
        document_tasks,
        "DatabaseVectorIndex",
        FakeVectorIndex,
    )

    async def successful_ingestion(
        session: AsyncSession,
        document_id: uuid.UUID,
        storage: object,
        vector_index: object,
        **kwargs: object,
    ) -> Document:
        candidate = await session.get(Document, document_id)
        assert candidate is not None
        candidate.ingestion_status = IngestionStatus.READY
        candidate.ingestion_error = None
        await session.commit()
        return candidate

    monkeypatch.setattr(
        document_tasks,
        "ingest_document",
        successful_ingestion,
    )

    result = await run_document_ingestion(document.id, task.id)

    assert result == str(document.id)
    await migrated_db_session.refresh(task)
    assert task.status is BackgroundTaskStatus.SUCCEEDED
    assert task.attempts == 1
    await migrated_db_session.refresh(document)
    assert document.ingestion_status is IngestionStatus.READY


async def test_finalize_failed_task_leaves_coherent_terminal_state(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document(status=IngestionStatus.PROCESSING)
    migrated_db_session.add(document)
    await migrated_db_session.flush()
    task = _task(document, status=BackgroundTaskStatus.RUNNING)
    migrated_db_session.add(task)
    await migrated_db_session.commit()

    monkeypatch.setattr(
        document_tasks,
        "async_session_factory",
        _session_factory(migrated_db_session),
    )

    await _finalize_failed_task(
        document.id,
        task.id,
        TransientIngestionError(INGESTION_ERROR_EMBEDDING),
    )

    await migrated_db_session.refresh(task)
    assert task.status is BackgroundTaskStatus.FAILED
    assert task.error_message == INGESTION_ERROR_EMBEDDING
    await migrated_db_session.refresh(document)
    assert document.ingestion_status is IngestionStatus.FAILED
    assert document.ingestion_error == INGESTION_TASK_FAILED


async def test_finalize_failed_task_preserves_ready_document(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document(status=IngestionStatus.READY)
    migrated_db_session.add(document)
    await migrated_db_session.flush()
    task = _task(document, status=BackgroundTaskStatus.RUNNING)
    migrated_db_session.add(task)
    await migrated_db_session.commit()

    monkeypatch.setattr(
        document_tasks,
        "async_session_factory",
        _session_factory(migrated_db_session),
    )

    await _finalize_failed_task(
        document.id,
        task.id,
        RuntimeError("worker failure after ingestion committed"),
    )

    await migrated_db_session.refresh(task)
    assert task.status is BackgroundTaskStatus.FAILED
    await migrated_db_session.refresh(document)
    assert document.ingestion_status is IngestionStatus.READY
