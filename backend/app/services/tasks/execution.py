from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_task import BackgroundTask
from app.models.enums import BackgroundTaskStatus

DOCUMENT_INGESTION_TASK_NAME = "documents.ingest_document"


def create_background_task(
    *,
    task_name: str,
    celery_task_id: str,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
) -> BackgroundTask:
    return BackgroundTask(
        task_name=task_name,
        celery_task_id=celery_task_id,
        status=BackgroundTaskStatus.PENDING,
        resource_type=resource_type,
        resource_id=resource_id,
    )


async def mark_background_task_running(
    session: AsyncSession,
    background_task_id: uuid.UUID,
) -> BackgroundTask | None:
    task = await session.get(BackgroundTask, background_task_id)
    if task is None:
        return None
    task.status = BackgroundTaskStatus.RUNNING
    task.started_at = datetime.now(UTC)
    task.finished_at = None
    task.error_message = None
    task.attempts += 1
    return task


async def mark_background_task_succeeded(
    session: AsyncSession,
    background_task_id: uuid.UUID,
) -> BackgroundTask | None:
    task = await session.get(BackgroundTask, background_task_id)
    if task is None:
        return None
    task.status = BackgroundTaskStatus.SUCCEEDED
    task.finished_at = datetime.now(UTC)
    task.error_message = None
    return task


async def mark_background_task_failed(
    session: AsyncSession,
    background_task_id: uuid.UUID,
    error_message: str,
) -> BackgroundTask | None:
    task = await session.get(BackgroundTask, background_task_id)
    if task is None:
        return None
    task.status = BackgroundTaskStatus.FAILED
    task.finished_at = datetime.now(UTC)
    task.error_message = error_message[:2000]
    return task


__all__ = [
    "DOCUMENT_INGESTION_TASK_NAME",
    "create_background_task",
    "mark_background_task_failed",
    "mark_background_task_running",
    "mark_background_task_succeeded",
]
