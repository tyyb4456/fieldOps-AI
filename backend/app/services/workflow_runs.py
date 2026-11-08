from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkflowRunStatus
from app.models.workflow_run import WorkflowRun
from app.schemas.workflow_run import (
    WorkflowRunCreate,
    WorkflowRunStatusUpdate,
)
from app.services import complaints as complaint_service
from app.services.authorization import AccessDeniedError

WORKFLOW_RUN_TRANSITIONS: dict[
    WorkflowRunStatus, frozenset[WorkflowRunStatus]
] = {
    WorkflowRunStatus.RUNNING: frozenset(
        {
            WorkflowRunStatus.PAUSED,
            WorkflowRunStatus.COMPLETED,
            WorkflowRunStatus.FAILED,
        }
    ),
    WorkflowRunStatus.PAUSED: frozenset(
        {
            WorkflowRunStatus.RUNNING,
            WorkflowRunStatus.COMPLETED,
            WorkflowRunStatus.FAILED,
        }
    ),
    WorkflowRunStatus.COMPLETED: frozenset(),
    WorkflowRunStatus.FAILED: frozenset(),
}

TERMINAL_WORKFLOW_RUN_STATUSES = frozenset(
    {WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED}
)


class WorkflowRunStateError(Exception):
    """Raised when a workflow-run lifecycle transition is not permitted."""


async def list_workflow_runs(
    session: AsyncSession,
    *,
    complaint_id: uuid.UUID | None,
    status: WorkflowRunStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[WorkflowRun], int]:
    filters = []
    if complaint_id is not None:
        filters.append(WorkflowRun.complaint_id == complaint_id)
    if status is not None:
        filters.append(WorkflowRun.status == status)

    total = await session.scalar(
        select(func.count()).select_from(WorkflowRun).where(*filters)
    )
    statement = (
        select(WorkflowRun)
        .where(*filters)
        .order_by(
            WorkflowRun.started_at.desc(),
            WorkflowRun.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(statement)
    return list(result.scalars().all()), int(total or 0)


async def get_workflow_run(
    session: AsyncSession,
    workflow_run_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> WorkflowRun:
    statement = select(WorkflowRun).where(
        WorkflowRun.id == workflow_run_id
    )
    if for_update:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    result = await session.execute(statement)
    workflow_run = result.scalar_one_or_none()
    if workflow_run is None:
        raise AccessDeniedError("Workflow run not found")
    return workflow_run


async def create_workflow_run(
    session: AsyncSession,
    *,
    complaint_id: uuid.UUID,
    data: WorkflowRunCreate,
) -> WorkflowRun:
    await complaint_service.get_complaint(session, complaint_id)

    workflow_run = WorkflowRun(
        complaint_id=complaint_id,
        status=WorkflowRunStatus.RUNNING,
        current_step=data.current_step,
    )
    session.add(workflow_run)
    await session.flush()
    return workflow_run


async def transition_workflow_run(
    session: AsyncSession,
    *,
    workflow_run_id: uuid.UUID,
    data: WorkflowRunStatusUpdate,
) -> WorkflowRun:
    workflow_run = await get_workflow_run(
        session,
        workflow_run_id,
        for_update=True,
    )
    current_status = workflow_run.status
    target_status = data.status

    if target_status is current_status:
        raise WorkflowRunStateError(
            "Workflow run is already in the requested state"
        )
    if current_status in TERMINAL_WORKFLOW_RUN_STATUSES:
        raise WorkflowRunStateError(
            "Terminal workflow runs cannot be transitioned"
        )

    allowed = WORKFLOW_RUN_TRANSITIONS.get(
        current_status,
        frozenset(),
    )
    if target_status not in allowed:
        raise WorkflowRunStateError(
            f"Cannot move workflow run from {current_status.value} "
            f"to {target_status.value}"
        )

    if data.current_step is not None:
        workflow_run.current_step = data.current_step

    workflow_run.status = target_status

    if target_status in TERMINAL_WORKFLOW_RUN_STATUSES:
        workflow_run.finished_at = datetime.now(timezone.utc)
    else:
        workflow_run.finished_at = None

    if target_status is WorkflowRunStatus.FAILED:
        workflow_run.error_message = data.error_message
    else:
        workflow_run.error_message = None

    await session.flush()
    return workflow_run
