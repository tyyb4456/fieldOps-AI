from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import WorkflowRunStatus, WorkflowRunType
from app.models.user import User
from app.models.workflow_run import WorkflowRun
from app.services.diagnostics.diagnostics import (
    DiagnosticService,
    get_complaint_for_operations_user,
)
from app.services.rag.vector_index import VectorIndex
from app.services.tasks.execution import (
    DIAGNOSTIC_INVESTIGATION_TASK_NAME,
    WORK_ORDER_PROPOSAL_TASK_NAME,
    create_background_task,
    mark_background_task_failed,
)
from app.services.tasks.outbox import (
    create_outbox_event,
    dispatch_outbox_event,
)
from app.services.work_orders.work_order_proposals import (
    WorkOrderProposalService,
)
from app.services.workflows.executor import (
    execute_workflow,
    workflow_failure_message,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PendingWorkflow:
    """Durably queued workflow awaiting inline execution or broker dispatch."""

    workflow_run: WorkflowRun
    background_task_id: uuid.UUID
    outbox_event_id: uuid.UUID | None


async def _register_workflow(
    session: AsyncSession,
    workflow_run: WorkflowRun,
    *,
    task_name: str,
) -> PendingWorkflow:
    celery_task_id = str(uuid.uuid4())
    task = create_background_task(
        task_name=task_name,
        celery_task_id=celery_task_id,
        resource_type="workflow_run",
        resource_id=workflow_run.id,
    )
    session.add(task)
    await session.flush()

    if settings.celery_task_always_eager:
        return PendingWorkflow(
            workflow_run=workflow_run,
            background_task_id=task.id,
            outbox_event_id=None,
        )

    event = create_outbox_event(
        event_type=task_name,
        payload={
            "workflow_run_id": str(workflow_run.id),
            "background_task_id": str(task.id),
            "celery_task_id": celery_task_id,
            "args": [str(workflow_run.id), str(task.id)],
        },
    )
    session.add(event)
    await session.flush()
    return PendingWorkflow(
        workflow_run=workflow_run,
        background_task_id=task.id,
        outbox_event_id=event.id,
    )


async def schedule_diagnostic_investigation(
    session: AsyncSession,
    *,
    user: User,
    complaint_id: uuid.UUID,
    focus: str | None,
) -> PendingWorkflow:
    """Persist a diagnostic run, background task and outbox event atomically."""

    await get_complaint_for_operations_user(session, user, complaint_id)
    workflow_run = WorkflowRun(
        complaint_id=complaint_id,
        workflow_type=WorkflowRunType.DIAGNOSTIC_INVESTIGATION,
        requested_by_id=user.id,
        input_payload={"focus": (focus or "").strip()[:2000] or None},
        status=WorkflowRunStatus.RUNNING,
        current_step="queued",
    )
    session.add(workflow_run)
    await session.flush()

    try:
        pending = await _register_workflow(
            session,
            workflow_run,
            task_name=DIAGNOSTIC_INVESTIGATION_TASK_NAME,
        )
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    return pending


async def schedule_work_order_proposal(
    session: AsyncSession,
    *,
    user: User,
    complaint_id: uuid.UUID,
    proposal_service: WorkOrderProposalService,
) -> PendingWorkflow:
    """Validate and persist a proposal run, task and outbox event atomically."""

    await proposal_service.validate_generation_context(
        session=session,
        user=user,
        complaint_id=complaint_id,
    )
    workflow_run = WorkflowRun(
        complaint_id=complaint_id,
        workflow_type=WorkflowRunType.WORK_ORDER_PROPOSAL,
        requested_by_id=user.id,
        input_payload={},
        status=WorkflowRunStatus.RUNNING,
        current_step="queued",
    )
    session.add(workflow_run)
    await session.flush()

    try:
        pending = await _register_workflow(
            session,
            workflow_run,
            task_name=WORK_ORDER_PROPOSAL_TASK_NAME,
        )
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    return pending


async def _run_inline(
    session: AsyncSession,
    pending: PendingWorkflow,
    *,
    vector_index: VectorIndex,
    diagnostic_service: DiagnosticService | None,
    proposal_service: WorkOrderProposalService | None,
) -> WorkflowRun:
    workflow_run_id = pending.workflow_run.id
    background_task_id = pending.background_task_id
    try:
        workflow_run = await execute_workflow(
            session,
            workflow_run_id=workflow_run_id,
            vector_index=vector_index,
            diagnostic_service=diagnostic_service,
            proposal_service=proposal_service,
        )
        await session.commit()
        return workflow_run
    except Exception as exc:
        await session.rollback()
        failed_run = await session.get(WorkflowRun, workflow_run_id)
        if failed_run is None:
            raise
        failed_run.status = WorkflowRunStatus.FAILED
        failed_run.current_step = "failed"
        failed_run.error_message = workflow_failure_message(exc)[:2000]
        await mark_background_task_failed(
            session,
            background_task_id,
            workflow_failure_message(exc),
        )
        await session.commit()
        logger.error(
            "Inline workflow execution failed",
            extra={
                "event": "workflow_inline_failed",
                "workflow_run_id": str(workflow_run_id),
                "error_type": type(exc).__name__,
            },
        )
        return failed_run


async def start_workflow(
    session: AsyncSession,
    pending: PendingWorkflow,
    *,
    vector_index: VectorIndex,
    diagnostic_service: DiagnosticService | None = None,
    proposal_service: WorkOrderProposalService | None = None,
) -> WorkflowRun:
    """Run inline when eager, otherwise publish a best-effort outbox event."""

    if settings.celery_task_always_eager:
        return await _run_inline(
            session,
            pending,
            vector_index=vector_index,
            diagnostic_service=diagnostic_service,
            proposal_service=proposal_service,
        )

    if pending.outbox_event_id is not None:
        published = await dispatch_outbox_event(
            session,
            pending.outbox_event_id,
        )
        if not published:
            logger.warning(
                "Workflow queued for later outbox dispatch",
                extra={
                    "event": "workflow_enqueue_deferred",
                    "workflow_run_id": str(pending.workflow_run.id),
                    "background_task_id": str(pending.background_task_id),
                },
            )
    return pending.workflow_run


async def enqueue_diagnostic_investigation(
    session: AsyncSession,
    *,
    user: User,
    complaint_id: uuid.UUID,
    focus: str | None,
    vector_index: VectorIndex,
    diagnostic_service: DiagnosticService | None = None,
) -> WorkflowRun:
    pending = await schedule_diagnostic_investigation(
        session,
        user=user,
        complaint_id=complaint_id,
        focus=focus,
    )
    return await start_workflow(
        session,
        pending,
        vector_index=vector_index,
        diagnostic_service=diagnostic_service,
    )


async def enqueue_work_order_proposal(
    session: AsyncSession,
    *,
    user: User,
    complaint_id: uuid.UUID,
    vector_index: VectorIndex,
    proposal_service: WorkOrderProposalService,
) -> WorkflowRun:
    pending = await schedule_work_order_proposal(
        session,
        user=user,
        complaint_id=complaint_id,
        proposal_service=proposal_service,
    )
    return await start_workflow(
        session,
        pending,
        vector_index=vector_index,
        proposal_service=proposal_service,
    )


__all__ = [
    "PendingWorkflow",
    "enqueue_diagnostic_investigation",
    "enqueue_work_order_proposal",
    "schedule_diagnostic_investigation",
    "schedule_work_order_proposal",
    "start_workflow",
]
