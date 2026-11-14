from __future__ import annotations

import logging
import uuid

from app.celery_app import celery_app
from app.core.config import settings
from app.db.session import async_session_factory, engine, run_async_task
from app.models.background_task import BackgroundTask
from app.models.document import Document
from app.models.enums import BackgroundTaskStatus, IngestionStatus
from app.services.documents.document_ingestion import (
    IngestionInProgressError,
    ingest_document,
)
from app.services.documents.storage import build_document_storage
from app.services.rag.embeddings import get_embedding_provider
from app.services.rag.vector_index import DatabaseVectorIndex
from app.services.shared.retry import is_transient_error
from app.services.tasks.execution import (
    DOCUMENT_INGESTION_TASK_NAME,
    mark_background_task_failed,
    mark_background_task_running,
    mark_background_task_succeeded,
)

logger = logging.getLogger(__name__)

INGESTION_TASK_FAILED = "The document ingestion task failed."


def _retry_countdown(retries: int) -> int:
    delay = settings.celery_task_retry_backoff_seconds * (2**retries)
    return min(delay, settings.celery_task_retry_backoff_max_seconds)


def _should_retry(exc: BaseException) -> bool:
    """Retry transient provider/infra failures and in-progress conflicts only."""

    return isinstance(exc, IngestionInProgressError) or is_transient_error(exc)


async def run_document_ingestion(
    document_id: uuid.UUID,
    background_task_id: uuid.UUID | None = None,
) -> str:
    async with async_session_factory() as session:
        if background_task_id is not None:
            task = await session.get(BackgroundTask, background_task_id)
            if task is not None and task.status in (
                BackgroundTaskStatus.SUCCEEDED,
                BackgroundTaskStatus.CANCELLED,
            ):
                logger.info(
                    "Skipping duplicate delivery for terminal background task",
                    extra={
                        "event": "document_ingestion_duplicate_skipped",
                        "document_id": str(document_id),
                        "background_task_id": str(background_task_id),
                        "background_task_status": task.status.value,
                    },
                )
                return str(document_id)

            await mark_background_task_running(session, background_task_id)
            await session.commit()

        storage = build_document_storage(settings)
        embedding_provider = get_embedding_provider()
        vector_index = DatabaseVectorIndex(
            engine=engine,
            embedding_provider=embedding_provider,
            owns_engine=False,
        )
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
        finally:
            await vector_index.close()

        if background_task_id is not None:
            if document.ingestion_status is IngestionStatus.READY:
                await mark_background_task_succeeded(
                    session,
                    background_task_id,
                )
            else:
                await mark_background_task_failed(
                    session,
                    background_task_id,
                    document.ingestion_error or INGESTION_TASK_FAILED,
                )
            await session.commit()

        return str(document.id)


async def _finalize_failed_task(
    document_id: uuid.UUID,
    background_task_id: uuid.UUID | None,
    error: Exception,
) -> None:
    message = str(error) or type(error).__name__
    async with async_session_factory() as session:
        if background_task_id is not None:
            await mark_background_task_failed(
                session,
                background_task_id,
                message,
            )
        document = await session.get(Document, document_id)
        if (
            document is not None
            and not isinstance(error, IngestionInProgressError)
            and document.ingestion_status
            not in (IngestionStatus.READY, IngestionStatus.FAILED)
        ):
            document.ingestion_status = IngestionStatus.FAILED
            document.ingestion_error = INGESTION_TASK_FAILED
            document.ingestion_started_at = None
            document.is_active = False
        await session.commit()

    logger.error(
        "Document ingestion task failed",
        extra={
            "event": "document_ingestion_task_failed",
            "document_id": str(document_id),
            "error_type": type(error).__name__,
        },
    )


@celery_app.task(
    bind=True,
    name=DOCUMENT_INGESTION_TASK_NAME,
    acks_late=True,
    track_started=True,
)
def ingest_document_task(
    self,
    document_id: str,
    background_task_id: str | None = None,
) -> str:
    document_uuid = uuid.UUID(document_id)
    task_uuid = uuid.UUID(background_task_id) if background_task_id else None
    try:
        return run_async_task(
            run_document_ingestion(document_uuid, task_uuid),
            engine=engine,
        )
    except Exception as exc:
        if (
            _should_retry(exc)
            and self.request.retries < settings.celery_task_max_retries
        ):
            raise self.retry(
                exc=exc,
                countdown=_retry_countdown(self.request.retries),
            )
        run_async_task(
            _finalize_failed_task(document_uuid, task_uuid, exc),
            engine=engine,
        )
        raise


__all__ = [
    "ingest_document_task",
    "run_document_ingestion",
]
