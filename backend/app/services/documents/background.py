from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.models.enums import IngestionStatus
from app.services.documents import documents as document_service
from app.services.documents.document_ingestion import (
    IngestionInProgressError,
    UploadedPdf,
    ingest_document,
)
from app.services.documents.storage import DocumentStorage
from app.services.rag.vector_index import VectorIndex
from app.services.shared.authorization import AccessDeniedError
from app.services.tasks.execution import (
    DOCUMENT_INGESTION_TASK_NAME,
    create_background_task,
    mark_background_task_failed,
    mark_background_task_running,
    mark_background_task_succeeded,
)
from app.services.tasks.outbox import (
    create_outbox_event,
    dispatch_outbox_event,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PendingIngestion:
    """Durably queued ingestion awaiting an inline run or broker dispatch."""

    document: Document
    background_task_id: uuid.UUID
    outbox_event_id: uuid.UUID | None


async def _register_ingestion(
    session: AsyncSession,
    document: Document,
) -> PendingIngestion:
    """Add the background task and outbox event to the current transaction.

    The caller commits document, task and outbox rows together so the queue
    intent is durable before any broker publish is attempted. Eager mode skips
    the outbox and runs ingestion inline instead.
    """

    celery_task_id = str(uuid.uuid4())
    task = create_background_task(
        task_name=DOCUMENT_INGESTION_TASK_NAME,
        celery_task_id=celery_task_id,
        resource_type="document",
        resource_id=document.id,
    )
    session.add(task)
    await session.flush()

    if settings.celery_task_always_eager:
        return PendingIngestion(
            document=document,
            background_task_id=task.id,
            outbox_event_id=None,
        )

    event = create_outbox_event(
        event_type=DOCUMENT_INGESTION_TASK_NAME,
        payload={
            "document_id": str(document.id),
            "background_task_id": str(task.id),
            "celery_task_id": celery_task_id,
        },
    )
    session.add(event)
    await session.flush()
    return PendingIngestion(
        document=document,
        background_task_id=task.id,
        outbox_event_id=event.id,
    )


async def create_uploaded_ingestion(
    session: AsyncSession,
    *,
    uploaded: UploadedPdf,
    storage_key: str,
    manufacturer: str,
    model: str,
    document_name: str,
    version: str | None,
    uploaded_by_id: uuid.UUID,
) -> PendingIngestion:
    """Persist an uploaded document with its task and outbox event atomically."""

    try:
        document = await document_service.create_uploaded_document(
            session,
            uploaded=uploaded,
            storage_key=storage_key,
            manufacturer=manufacturer,
            model=model,
            document_name=document_name,
            version=version,
            uploaded_by_id=uploaded_by_id,
        )
        pending = await _register_ingestion(session, document)
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    return pending


async def start_ingestion(
    session: AsyncSession,
    pending: PendingIngestion,
    *,
    storage: DocumentStorage,
    vector_index: VectorIndex,
) -> Document:
    """Run the ingestion inline or publish its outbox event best-effort.

    A failed broker publish is not fatal: the outbox row remains pending and is
    published by a later dispatcher run, so the API still returns the durably
    queued document.
    """

    if settings.celery_task_always_eager:
        return await _run_inline(
            session,
            pending.document.id,
            pending.background_task_id,
            storage=storage,
            vector_index=vector_index,
        )

    if pending.outbox_event_id is not None:
        published = await dispatch_outbox_event(session, pending.outbox_event_id)
        if not published:
            logger.warning(
                "Document ingestion queued for later outbox dispatch",
                extra={
                    "event": "document_ingestion_enqueue_deferred",
                    "document_id": str(pending.document.id),
                    "background_task_id": str(pending.background_task_id),
                },
            )
    return pending.document


async def enqueue_uploaded_document_ingestion(
    session: AsyncSession,
    *,
    uploaded: UploadedPdf,
    storage_key: str,
    manufacturer: str,
    model: str,
    document_name: str,
    version: str | None,
    uploaded_by_id: uuid.UUID,
    storage: DocumentStorage,
    vector_index: VectorIndex,
) -> Document:
    pending = await create_uploaded_ingestion(
        session,
        uploaded=uploaded,
        storage_key=storage_key,
        manufacturer=manufacturer,
        model=model,
        document_name=document_name,
        version=version,
        uploaded_by_id=uploaded_by_id,
    )
    return await start_ingestion(
        session,
        pending,
        storage=storage,
        vector_index=vector_index,
    )


async def enqueue_document_ingestion(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    storage: DocumentStorage,
    vector_index: VectorIndex,
) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise AccessDeniedError("Document not found")
    if document.ingestion_status is IngestionStatus.PROCESSING:
        raise IngestionInProgressError("Document ingestion is already in progress.")

    pending = await _register_ingestion(session, document)
    await session.commit()
    return await start_ingestion(
        session,
        pending,
        storage=storage,
        vector_index=vector_index,
    )


async def _run_inline(
    session: AsyncSession,
    document_id: uuid.UUID,
    background_task_id: uuid.UUID,
    *,
    storage: DocumentStorage,
    vector_index: VectorIndex,
) -> Document:
    await mark_background_task_running(session, background_task_id)
    await session.commit()

    try:
        document = await ingest_document(
            session,
            document_id,
            storage,
            vector_index,
            max_pages=settings.max_pdf_pages,
            chunk_size=settings.document_chunk_size,
            chunk_overlap=settings.document_chunk_overlap,
            ingestion_version=settings.document_ingestion_version,
        )
    except Exception as exc:
        await mark_background_task_failed(
            session,
            background_task_id,
            str(exc) or type(exc).__name__,
        )
        await session.commit()
        raise

    if document.ingestion_status is IngestionStatus.READY:
        await mark_background_task_succeeded(session, background_task_id)
    else:
        await mark_background_task_failed(
            session,
            background_task_id,
            document.ingestion_error or "Document ingestion failed.",
        )
    await session.commit()
    return document


__all__ = [
    "PendingIngestion",
    "create_uploaded_ingestion",
    "enqueue_document_ingestion",
    "enqueue_uploaded_document_ingestion",
    "start_ingestion",
]
