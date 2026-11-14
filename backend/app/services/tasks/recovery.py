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
    WorkflowRunStatus,
)
from app.models.outbox_event import OutboxEvent
from app.models.work_order_proposal import WorkOrderProposal
from app.models.workflow_run import WorkflowRun
from app.services.tasks.execution import (
    workflow_execution_stale_after_seconds,
)

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
RECONCILED_WORKFLOW_ERROR = (
    "The workflow was never dispatched and was failed by operator "
    "reconciliation. Start a new run."
)
RECONCILED_RUNNING_TASK_ERROR = (
    "The running workflow task stopped without completing and was failed by "
    "operator reconciliation."
)
RECONCILED_RUNNING_WORKFLOW_ERROR = (
    "The running workflow stopped before completion and was failed by "
    "operator reconciliation. Start a new run."
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

        if (
            task.resource_type == "workflow_run"
            and task.resource_id is not None
        ):
            workflow_run = await session.get(
                WorkflowRun,
                task.resource_id,
                with_for_update=True,
            )
            if (
                workflow_run is not None
                and workflow_run.status
                in (
                    WorkflowRunStatus.RUNNING,
                    WorkflowRunStatus.PAUSED,
                )
            ):
                workflow_run.status = WorkflowRunStatus.FAILED
                workflow_run.current_step = "failed"
                workflow_run.finished_at = reference
                workflow_run.error_message = RECONCILED_WORKFLOW_ERROR

        reconciled.append(task.id)

    await session.commit()
    return tuple(reconciled)


async def fail_stale_running_tasks(
    session: AsyncSession,
    *,
    stale_after_seconds: int,
    now: datetime | None = None,
) -> tuple[uuid.UUID, ...]:
    """Fail stale RUNNING workflow tasks under an operator request.

    A healthy worker is killed by the Celery hard time limit before the
    minimum recovery age, and the linked workflow run and task rows are locked
    so the decision is serialized with worker completion. The effective age is
    never lower than the same safe claim window used by the worker, so this
    procedure cannot race a task that is still within its execution window.

    Tasks that are not workflow runs, including document ingestion, are left
    untouched. The operator must still start a new workflow run after
    recovery.

    A proposal workflow may have committed its proposal in an earlier
    transaction and then lost its worker before the run and task were
    finalized. The ``source_workflow_run_id`` link proves the proposal belongs
    to this run, so the run and task are reconciled to success with that
    proposal instead of being failed. The unique constraint on the link
    guarantees there is at most one proposal to recover.
    """

    reference = now or datetime.now(UTC)
    effective_stale_after = max(
        stale_after_seconds,
        workflow_execution_stale_after_seconds(),
    )
    threshold = reference - timedelta(seconds=effective_stale_after)
    candidates = (
        await session.execute(
            select(BackgroundTask.id, BackgroundTask.resource_id)
            .where(
                BackgroundTask.status == BackgroundTaskStatus.RUNNING,
                BackgroundTask.resource_type == "workflow_run",
                func.coalesce(
                    BackgroundTask.started_at,
                    BackgroundTask.created_at,
                )
                < threshold,
            )
            .order_by(
                BackgroundTask.created_at.asc(),
                BackgroundTask.id.asc(),
            )
        )
    ).all()

    reconciled: list[uuid.UUID] = []
    for background_task_id, resource_id in candidates:
        # Lock the workflow run before its task so this path has the same
        # order as worker completion and cannot deadlock with it.
        workflow_run: WorkflowRun | None = None
        if resource_id is not None:
            workflow_run = await session.get(
                WorkflowRun,
                resource_id,
                with_for_update=True,
                populate_existing=True,
            )
        task = await session.get(
            BackgroundTask,
            background_task_id,
            with_for_update=True,
            populate_existing=True,
        )
        if task is None or task.status is not BackgroundTaskStatus.RUNNING:
            continue
        started_at = task.started_at or task.created_at
        if started_at >= threshold:
            continue

        recovered_proposal: WorkOrderProposal | None = None
        if (
            workflow_run is not None
            and workflow_run.status
            in (
                WorkflowRunStatus.RUNNING,
                WorkflowRunStatus.PAUSED,
            )
        ):
            # Lock the proposal for the same run so an approval or rejection
            # cannot change its status between this read and the commit.
            recovered_proposal = (
                await session.execute(
                    select(WorkOrderProposal)
                    .where(
                        WorkOrderProposal.source_workflow_run_id
                        == workflow_run.id
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()

        if (
            workflow_run is not None
            and workflow_run.status is WorkflowRunStatus.COMPLETED
        ):
            task.status = BackgroundTaskStatus.SUCCEEDED
            task.finished_at = reference
            task.error_message = None
        elif (
            workflow_run is not None
            and workflow_run.status is WorkflowRunStatus.FAILED
        ):
            task.status = BackgroundTaskStatus.FAILED
            task.finished_at = reference
            task.error_message = (
                workflow_run.error_message or RECONCILED_TASK_ERROR
            )[:2000]
        elif recovered_proposal is not None and workflow_run is not None:
            task.status = BackgroundTaskStatus.SUCCEEDED
            task.finished_at = reference
            task.error_message = None
            workflow_run.status = WorkflowRunStatus.COMPLETED
            workflow_run.current_step = "completed"
            workflow_run.finished_at = reference
            workflow_run.error_message = None
            workflow_run.result_payload = {
                "proposal_id": str(recovered_proposal.id),
                "status": recovered_proposal.status.value,
            }
        else:
            task.status = BackgroundTaskStatus.FAILED
            task.finished_at = reference
            task.error_message = RECONCILED_RUNNING_TASK_ERROR
            if workflow_run is not None:
                workflow_run.status = WorkflowRunStatus.FAILED
                workflow_run.current_step = "failed"
                workflow_run.finished_at = reference
                workflow_run.error_message = RECONCILED_RUNNING_WORKFLOW_ERROR

        reconciled.append(task.id)

    await session.commit()
    return tuple(reconciled)


__all__ = [
    "RECONCILED_DOCUMENT_ERROR",
    "RECONCILED_OUTBOX_ERROR",
    "RECONCILED_RUNNING_TASK_ERROR",
    "RECONCILED_RUNNING_WORKFLOW_ERROR",
    "RECONCILED_TASK_ERROR",
    "RECONCILED_WORKFLOW_ERROR",
    "ReconciliationReport",
    "fail_stale_pending_tasks",
    "fail_stale_running_tasks",
    "inspect_background_tasks",
]
