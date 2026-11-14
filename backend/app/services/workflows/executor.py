from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.background_task import BackgroundTask
from app.models.enums import (
    BackgroundTaskStatus,
    WorkflowRunStatus,
    WorkflowRunType,
)
from app.models.user import User
from app.models.work_order_proposal import WorkOrderProposal
from app.models.workflow_run import WorkflowRun
from app.services.diagnostics.diagnostics import (
    DiagnosticResult,
    DiagnosticService,
    get_complaint_for_operations_user,
)
from app.services.rag.vector_index import VectorIndex
from app.services.work_orders.work_order_proposals import (
    WorkOrderProposalService,
)
from app.services.workflows.diagnostic_graph import (
    ProgressCallback,
    build_diagnostic_graph,
)
from app.services.workflows.errors import (
    WorkflowExecutionError,
    WorkflowOwnershipLostError,
    WorkflowPermanentError,
    classify_workflow_error,
    safe_workflow_error_message,
)
from app.services.workflows.factories import (
    build_diagnostic_service,
    build_work_order_proposal_service,
)
from app.services.workflows.proposal_graph import build_proposal_graph
from app.services.workflows.serialization import diagnostic_result_payload

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset(
    {
        WorkflowRunStatus.COMPLETED,
        WorkflowRunStatus.FAILED,
    }
)


async def _load_workflow_run(
    session: AsyncSession,
    workflow_run_id: uuid.UUID,
) -> WorkflowRun:
    workflow_run = await session.get(WorkflowRun, workflow_run_id)
    if workflow_run is None:
        raise WorkflowPermanentError("The workflow run no longer exists.")
    return workflow_run


async def _load_requester(
    session: AsyncSession,
    workflow_run: WorkflowRun,
) -> User:
    if workflow_run.requested_by_id is None:
        raise WorkflowPermanentError(
            "The workflow run has no requesting operator."
        )
    user = await session.get(User, workflow_run.requested_by_id)
    if user is None or not user.is_active:
        raise WorkflowPermanentError(
            "The requesting operator is no longer available."
        )
    return user


def _claim_exists(
    background_task_id: uuid.UUID,
    claimed_started_at: datetime,
) -> ColumnElement[bool]:
    return (
        select(BackgroundTask.id)
        .where(
            BackgroundTask.id == background_task_id,
            BackgroundTask.status == BackgroundTaskStatus.RUNNING,
            BackgroundTask.started_at == claimed_started_at,
        )
        .exists()
    )


def _make_step_callback(
    session: AsyncSession,
    workflow_run_id: uuid.UUID,
    *,
    background_task_id: uuid.UUID | None = None,
    claimed_started_at: datetime | None = None,
) -> ProgressCallback:
    async def on_step(step: str) -> None:
        statement = (
            update(WorkflowRun)
            .where(
                WorkflowRun.id == workflow_run_id,
                WorkflowRun.status == WorkflowRunStatus.RUNNING,
            )
            .values(current_step=step)
            .returning(WorkflowRun.id)
            .execution_options(synchronize_session=False)
        )
        if background_task_id is not None and claimed_started_at is not None:
            statement = statement.where(
                _claim_exists(background_task_id, claimed_started_at)
            )
        updated = (await session.execute(statement)).scalar_one_or_none()
        await session.commit()
        if updated is None:
            raise WorkflowOwnershipLostError(
                "The workflow execution ownership was lost."
            )

    return on_step


async def execute_workflow(
    session: AsyncSession,
    *,
    workflow_run_id: uuid.UUID,
    vector_index: VectorIndex,
    diagnostic_service: DiagnosticService | None = None,
    proposal_service: WorkOrderProposalService | None = None,
    background_task_id: uuid.UUID | None = None,
    claimed_started_at: datetime | None = None,
) -> WorkflowRun:
    """Execute one complete LangGraph workflow for a persisted run.

    The caller owns the transaction and must commit on success and roll back
    on failure. Workflow nodes update progress with short commits so status
    reads do not depend on Celery's result backend.

    When a background-task claim is supplied, every progress commit and the
    final completion update are fenced by that claim. A worker that lost its
    claim stops before the next graph step and can never overwrite the state
    owned by a recovered execution.
    """

    workflow_run = await _load_workflow_run(session, workflow_run_id)
    if workflow_run.status in TERMINAL_STATUSES:
        logger.info(
            "Skipping workflow execution for terminal run",
            extra={
                "event": "workflow_run_terminal_skip",
                "workflow_run_id": str(workflow_run.id),
                "workflow_status": workflow_run.status.value,
            },
        )
        return workflow_run
    if workflow_run.workflow_type is None:
        raise WorkflowPermanentError(
            "The workflow run has no executable workflow type."
        )

    user = await _load_requester(session, workflow_run)
    focus = (
        workflow_run.input_payload.get("focus")
        if isinstance(workflow_run.input_payload, dict)
        else None
    )
    on_step = _make_step_callback(
        session,
        workflow_run.id,
        background_task_id=background_task_id,
        claimed_started_at=claimed_started_at,
    )

    try:
        if workflow_run.workflow_type is WorkflowRunType.DIAGNOSTIC_INVESTIGATION:
            diagnostic = diagnostic_service or build_diagnostic_service()
            graph = build_diagnostic_graph(
                service=diagnostic,
                session=session,
                user=user,
                vector_index=vector_index,
                on_step=on_step,
            )
            state = await graph.ainvoke(
                {
                    "complaint_id": str(workflow_run.complaint_id),
                    "focus": focus if isinstance(focus, str) else None,
                }
            )
            diagnosis = state.get("diagnosis")
            if not isinstance(diagnosis, DiagnosticResult):
                raise WorkflowPermanentError(
                    "The diagnostic workflow did not return a result."
                )
            workflow_run.result_payload = diagnostic_result_payload(diagnosis)
        elif workflow_run.workflow_type is WorkflowRunType.WORK_ORDER_PROPOSAL:
            await get_complaint_for_operations_user(
                session,
                user,
                workflow_run.complaint_id,
            )
            recovered_proposal_id = await session.scalar(
                select(WorkOrderProposal.id).where(
                    WorkOrderProposal.source_workflow_run_id == workflow_run.id
                )
            )
            if recovered_proposal_id is not None:
                logger.info(
                    "Recovering proposal persisted before workflow completion",
                    extra={
                        "event": "workflow_proposal_run_recovered",
                        "workflow_run_id": str(workflow_run.id),
                        "proposal_id": str(recovered_proposal_id),
                    },
                )
                workflow_run.result_payload = {
                    "proposal_id": str(recovered_proposal_id),
                    "status": "pending_approval",
                }
            else:
                if proposal_service is not None:
                    prep_service = proposal_service
                    diagnostic = (
                        diagnostic_service or prep_service.diagnostic_service
                    )
                else:
                    diagnostic = diagnostic_service or build_diagnostic_service()
                    prep_service = build_work_order_proposal_service(
                        diagnostic_service=diagnostic
                    )
                graph = build_proposal_graph(
                    proposal_service=prep_service,
                    diagnostic_service=diagnostic,
                    session=session,
                    user=user,
                    vector_index=vector_index,
                    on_step=on_step,
                    workflow_run_id=workflow_run.id,
                )
                state = await graph.ainvoke(
                    {
                        "complaint_id": str(workflow_run.complaint_id),
                    }
                )
                proposal_id = state.get("proposal_id")
                if not isinstance(proposal_id, str):
                    raise WorkflowPermanentError(
                        "The proposal workflow did not persist a proposal."
                    )
                workflow_run.result_payload = {
                    "proposal_id": proposal_id,
                    "status": "pending_approval",
                }
        else:
            raise WorkflowPermanentError(
                "The workflow type is not supported."
            )
    except WorkflowExecutionError:
        raise
    except Exception as exc:
        classified = classify_workflow_error(exc)
        raise classified from exc

    now = datetime.now(UTC)
    completion_values = {
        "result_payload": workflow_run.result_payload,
        "status": WorkflowRunStatus.COMPLETED,
        "current_step": "completed",
        "finished_at": now,
        "error_message": None,
    }
    completion = (
        update(WorkflowRun)
        .where(
            WorkflowRun.id == workflow_run.id,
            WorkflowRun.status == WorkflowRunStatus.RUNNING,
        )
        .values(**completion_values)
        .returning(WorkflowRun.id)
        .execution_options(synchronize_session=False)
    )
    if background_task_id is not None and claimed_started_at is not None:
        completion = completion.where(
            _claim_exists(background_task_id, claimed_started_at)
        )
    completed = (await session.execute(completion)).scalar_one_or_none()
    if completed is None:
        raise WorkflowOwnershipLostError(
            "The workflow execution ownership was lost."
        )

    for field, value in completion_values.items():
        setattr(workflow_run, field, value)
    await session.flush()
    return workflow_run


def workflow_failure_message(exc: BaseException) -> str:
    return safe_workflow_error_message(exc)


__all__ = [
    "TERMINAL_STATUSES",
    "execute_workflow",
    "workflow_failure_message",
]
