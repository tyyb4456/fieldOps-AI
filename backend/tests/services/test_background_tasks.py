from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import BackgroundTaskStatus
from app.services.tasks.execution import (
    DOCUMENT_INGESTION_TASK_NAME,
    create_background_task,
    mark_background_task_failed,
    mark_background_task_running,
    mark_background_task_succeeded,
)


async def test_background_task_status_transitions(
    migrated_db_session: AsyncSession,
) -> None:
    resource_id = uuid.uuid4()
    task = create_background_task(
        task_name=DOCUMENT_INGESTION_TASK_NAME,
        celery_task_id=str(uuid.uuid4()),
        resource_type="document",
        resource_id=resource_id,
    )
    migrated_db_session.add(task)
    await migrated_db_session.commit()
    await migrated_db_session.refresh(task)

    assert task.status is BackgroundTaskStatus.PENDING
    assert task.attempts == 0
    assert task.resource_id == resource_id

    await mark_background_task_running(migrated_db_session, task.id)
    await migrated_db_session.commit()

    assert task.status is BackgroundTaskStatus.RUNNING
    assert task.attempts == 1
    assert task.started_at is not None

    await mark_background_task_succeeded(migrated_db_session, task.id)
    await migrated_db_session.commit()

    assert task.status is BackgroundTaskStatus.SUCCEEDED
    assert task.finished_at is not None
    assert task.error_message is None

    await mark_background_task_failed(
        migrated_db_session,
        task.id,
        "task failed",
    )
    await migrated_db_session.commit()

    assert task.status is BackgroundTaskStatus.FAILED
    assert task.error_message == "task failed"


async def test_missing_background_task_is_ignored(
    migrated_db_session: AsyncSession,
) -> None:
    missing_id = uuid.uuid4()

    assert (
        await mark_background_task_running(migrated_db_session, missing_id)
        is None
    )
    assert (
        await mark_background_task_succeeded(migrated_db_session, missing_id)
        is None
    )
    assert (
        await mark_background_task_failed(
            migrated_db_session,
            missing_id,
            "missing",
        )
        is None
    )
