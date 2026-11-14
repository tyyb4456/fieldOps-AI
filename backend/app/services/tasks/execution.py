from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.background_task import BackgroundTask
from app.models.enums import BackgroundTaskStatus

DOCUMENT_INGESTION_TASK_NAME = "documents.ingest_document"
DIAGNOSTIC_INVESTIGATION_TASK_NAME = "workflows.diagnostic_investigation"
WORK_ORDER_PROPOSAL_TASK_NAME = "workflows.work_order_proposal"

TERMINAL_BACKGROUND_TASK_STATUSES = frozenset(
    {
        BackgroundTaskStatus.SUCCEEDED,
        BackgroundTaskStatus.FAILED,
        BackgroundTaskStatus.CANCELLED,
    }
)

WORKFLOW_EXECUTION_STALE_AFTER_SECONDS = 30 * 60
WORKFLOW_EXECUTION_LEASE_MARGIN_SECONDS = 60


def workflow_execution_stale_after_seconds() -> int:
    """Return the safe age after which an uncompleted claim is recoverable.

    A Celery worker is killed by the hard time limit before this age, so an
    execution older than the returned threshold cannot still be healthy. The
    margin keeps the threshold above a task that is shutting down at the hard
    limit.
    """

    return max(
        WORKFLOW_EXECUTION_STALE_AFTER_SECONDS,
        settings.celery_task_time_limit_seconds
        + WORKFLOW_EXECUTION_LEASE_MARGIN_SECONDS,
    )


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


async def claim_background_task_execution(
    session: AsyncSession,
    background_task_id: uuid.UUID,
    *,
    stale_after_seconds: int | None = None,
    now: datetime | None = None,
) -> BackgroundTask | None:
    """Atomically claim exclusive execution ownership of a task.

    A task is claimable when it is still pending, or when a previous claim is
    older than the safe execution window. The conditional ``UPDATE`` is the
    ownership decision: two concurrent deliveries cannot both update the row,
    because the loser re-evaluates the predicate after the winner commits.

    The claim is committed before any model or retrieval call. No database lock
    or transaction is held while external operations run.
    """

    reference = now or datetime.now(UTC)
    threshold_seconds = (
        stale_after_seconds
        if stale_after_seconds is not None
        else workflow_execution_stale_after_seconds()
    )
    stale_before = reference - timedelta(seconds=threshold_seconds)
    statement = (
        update(BackgroundTask)
        .where(
            BackgroundTask.id == background_task_id,
            BackgroundTask.status.notin_(
                TERMINAL_BACKGROUND_TASK_STATUSES
            ),
            or_(
                BackgroundTask.status == BackgroundTaskStatus.PENDING,
                func.coalesce(
                    BackgroundTask.started_at,
                    BackgroundTask.created_at,
                )
                < stale_before,
            ),
        )
        .values(
            status=BackgroundTaskStatus.RUNNING,
            started_at=reference,
            finished_at=None,
            error_message=None,
            attempts=BackgroundTask.attempts + 1,
        )
        .returning(BackgroundTask.id)
        .execution_options(synchronize_session=False)
    )
    claimed_id = (await session.execute(statement)).scalar_one_or_none()
    await session.commit()
    if claimed_id is None:
        return None
    return await session.get(
        BackgroundTask,
        background_task_id,
        populate_existing=True,
    )


async def release_background_task_claim(
    session: AsyncSession,
    background_task_id: uuid.UUID,
    *,
    claimed_started_at: datetime,
) -> bool:
    """Return a claimed task to pending so Celery retries can re-claim it.

    Only the delivery that recorded ``claimed_started_at`` can release the
    claim. A release after another worker recovered the task is a no-op.
    """

    statement = (
        update(BackgroundTask)
        .where(
            BackgroundTask.id == background_task_id,
            BackgroundTask.status == BackgroundTaskStatus.RUNNING,
            BackgroundTask.started_at == claimed_started_at,
        )
        .values(
            status=BackgroundTaskStatus.PENDING,
            started_at=None,
            finished_at=None,
            error_message=None,
        )
        .returning(BackgroundTask.id)
        .execution_options(synchronize_session=False)
    )
    released = (
        await session.execute(statement)
    ).scalar_one_or_none() is not None
    await session.commit()
    return released


async def mark_claimed_background_task_succeeded(
    session: AsyncSession,
    background_task_id: uuid.UUID,
    *,
    claimed_started_at: datetime,
    now: datetime | None = None,
) -> bool:
    """Mark a task succeeded only while this delivery still owns the claim."""

    finished_at = now or datetime.now(UTC)
    statement = (
        update(BackgroundTask)
        .where(
            BackgroundTask.id == background_task_id,
            BackgroundTask.status == BackgroundTaskStatus.RUNNING,
            BackgroundTask.started_at == claimed_started_at,
        )
        .values(
            status=BackgroundTaskStatus.SUCCEEDED,
            finished_at=finished_at,
            error_message=None,
        )
        .returning(BackgroundTask.id)
        .execution_options(synchronize_session=False)
    )
    return (
        await session.execute(statement)
    ).scalar_one_or_none() is not None


async def mark_claimed_background_task_failed(
    session: AsyncSession,
    background_task_id: uuid.UUID,
    *,
    claimed_started_at: datetime,
    error_message: str,
    now: datetime | None = None,
) -> bool:
    """Mark a task failed only while this delivery still owns the claim."""

    finished_at = now or datetime.now(UTC)
    statement = (
        update(BackgroundTask)
        .where(
            BackgroundTask.id == background_task_id,
            BackgroundTask.status == BackgroundTaskStatus.RUNNING,
            BackgroundTask.started_at == claimed_started_at,
        )
        .values(
            status=BackgroundTaskStatus.FAILED,
            finished_at=finished_at,
            error_message=error_message[:2000],
        )
        .returning(BackgroundTask.id)
        .execution_options(synchronize_session=False)
    )
    return (
        await session.execute(statement)
    ).scalar_one_or_none() is not None


__all__ = [
    "DIAGNOSTIC_INVESTIGATION_TASK_NAME",
    "DOCUMENT_INGESTION_TASK_NAME",
    "TERMINAL_BACKGROUND_TASK_STATUSES",
    "WORKFLOW_EXECUTION_STALE_AFTER_SECONDS",
    "WORK_ORDER_PROPOSAL_TASK_NAME",
    "claim_background_task_execution",
    "create_background_task",
    "mark_background_task_failed",
    "mark_background_task_running",
    "mark_background_task_succeeded",
    "mark_claimed_background_task_failed",
    "mark_claimed_background_task_succeeded",
    "release_background_task_claim",
    "workflow_execution_stale_after_seconds",
]
