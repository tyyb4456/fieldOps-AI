from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_task import BackgroundTask
from app.models.document import Document
from app.models.enums import (
    BackgroundTaskStatus,
    IngestionStatus,
    OutboxEventStatus,
)
from app.models.outbox_event import OutboxEvent

RECONCILED_TASK_ERROR = (
    "The background task was never dispatched and was failed by operator "
    "reconciliation."
)
RECONCILED_DOCUMENT_ERROR = (
    "Document ingestion was never dispatched. Re-ingest the document."
)
RECONCILED_OUTBOX_ERROR = (
    "The outbox event was failed by operator reconciliation because its "
    "background task was never dispatched."
)


@dataclass(frozen=True)
class ReconciliationReport:
    stale_pending_tasks: tuple[uuid.UUID, ...]
    stale_running_tasks: tuple[uuid.UUID, ...]
    pending_outbox_events: int
    failed_outbox_events: int
    processing_documents: tuple[uuid.UUID, ...]

    @property
    def healthy(self) -> bool:
        return not (
            self.stale_pending_tasks
            or self.stale_running_tasks
            or self.failed_outbox_events
            or self.processing_documents
        )


async def inspect_background_tasks(
    session: AsyncSession,
    *,
    stale_after_seconds: int,
    now: datetime | None = None,
) -> ReconciliationReport:
    """Read-only reconciliation snapshot for operator diagnostics."""

    reference = now or datetime.now(UTC)
    threshold = reference - timedelta(seconds=stale_after_seconds)

    stale_pending = (
        await session.execute(
            select(BackgroundTask.id)
            .where(
                BackgroundTask.status == BackgroundTaskStatus.PENDING,
                BackgroundTask.created_at < threshold,
            )
            .order_by(BackgroundTask.created_at.asc())
        )
    ).scalars().all()

    stale_running = (
        await session.execute(
            select(BackgroundTask.id)
            .where(
                BackgroundTask.status == BackgroundTaskStatus.RUNNING,
                func.coalesce(
                    BackgroundTask.started_at,
                    BackgroundTask.created_at,
                )
                < threshold,
            )
            .order_by(BackgroundTask.created_at.asc())
        )
    ).scalars().all()

    outbox_counts = dict(
        (
            await session.execute(
                select(OutboxEvent.status, func.count()).group_by(
                    OutboxEvent.status
                )
            )
        ).all()
    )

    processing_documents = (
        await session.execute(
            select(Document.id)
            .where(Document.ingestion_status == IngestionStatus.PROCESSING)
            .order_by(Document.created_at.asc())
        )
    ).scalars().all()

    return ReconciliationReport(
        stale_pending_tasks=tuple(stale_pending),
        stale_running_tasks=tuple(stale_running),
        pending_outbox_events=int(
            outbox_counts.get(OutboxEventStatus.PENDING, 0)
        ),
        failed_outbox_events=int(
            outbox_counts.get(OutboxEventStatus.FAILED, 0)
        ),
        processing_documents=tuple(processing_documents),
    )


async def _load_task_outbox_events(
    session: AsyncSession,
    task_id: uuid.UUID,
) -> list[OutboxEvent]:
    """Lock and return every outbox event that references ``task_id``.

    The outbox payload is the only link between a background task and its
    dispatch record, so the JSONB field is queried directly. ``FOR UPDATE``
    serializes reconciliation with a dispatcher that may be publishing the same
    event.
    """

    statement = (
        select(OutboxEvent)
        .where(
            OutboxEvent.payload["background_task_id"].astext == str(task_id)
        )
        .order_by(OutboxEvent.created_at.asc(), OutboxEvent.id.asc())
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list((await session.execute(statement)).scalars().all())


async def fail_stale_pending_tasks(
    session: AsyncSession,
    *,
    stale_after_seconds: int,
    now: datetime | None = None,
) -> tuple[uuid.UUID, ...]:
    """Fail only stale PENDING tasks that no worker has started.

    RUNNING tasks are never touched because their worker may still be active and
    a stale RUNNING task is reported for manual inspection instead. Documents
    whose ingestion never started are moved to FAILED so they can be re-ingested.

    A stale task whose outbox event has already been published is left pending:
    the work was handed to the broker, so a worker may be about to start it and
    failing the task here would race with that worker. For tasks that were never
    published, the associated pending outbox events are failed in the same
    transaction so a later dispatcher cannot execute a task the operator has
    intentionally failed.
    """

    reference = now or datetime.now(UTC)
    threshold = reference - timedelta(seconds=stale_after_seconds)
    tasks = list(
        (
            await session.execute(
                select(BackgroundTask)
                .where(
                    BackgroundTask.status == BackgroundTaskStatus.PENDING,
                    BackgroundTask.created_at < threshold,
                )
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
    )

    reconciled: list[uuid.UUID] = []
    for task in tasks:
        outbox_events = await _load_task_outbox_events(session, task.id)
        if any(
            event.status is OutboxEventStatus.PUBLISHED
            for event in outbox_events
        ):
            continue

        task.status = BackgroundTaskStatus.FAILED
        task.finished_at = reference
        task.error_message = RECONCILED_TASK_ERROR

        for event in outbox_events:
            if event.status is OutboxEventStatus.PENDING:
                event.status = OutboxEventStatus.FAILED
                event.last_error = RECONCILED_OUTBOX_ERROR

        if task.resource_type == "document" and task.resource_id is not None:
            document = await session.get(
                Document,
                task.resource_id,
                with_for_update=True,
            )
            if (
                document is not None
                and document.ingestion_status is IngestionStatus.PENDING
            ):
                document.ingestion_status = IngestionStatus.FAILED
                document.ingestion_error = RECONCILED_DOCUMENT_ERROR
                document.ingestion_started_at = None
                document.is_active = False

        reconciled.append(task.id)

    await session.commit()
    return tuple(reconciled)


__all__ = [
    "RECONCILED_DOCUMENT_ERROR",
    "RECONCILED_OUTBOX_ERROR",
    "RECONCILED_TASK_ERROR",
    "ReconciliationReport",
    "fail_stale_pending_tasks",
    "inspect_background_tasks",
]
