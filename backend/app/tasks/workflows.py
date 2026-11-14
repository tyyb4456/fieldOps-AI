from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn

from app.celery_app import celery_app
from app.core.config import settings
from app.db.session import async_session_factory, engine, run_async_task
from app.models.background_task import BackgroundTask
from app.models.enums import BackgroundTaskStatus, WorkflowRunStatus
from app.models.workflow_run import WorkflowRun
from app.services.rag.embeddings import get_embedding_provider
from app.services.rag.vector_index import DatabaseVectorIndex
from app.services.shared.retry import is_transient_error
from app.services.tasks.execution import (
    DIAGNOSTIC_INVESTIGATION_TASK_NAME,
    WORK_ORDER_PROPOSAL_TASK_NAME,
    claim_background_task_execution,
    mark_background_task_failed,
    mark_background_task_succeeded,
    mark_claimed_background_task_succeeded,
    release_background_task_claim,
    workflow_execution_stale_after_seconds,
)
from app.services.workflows.errors import (
    WorkflowExecutionBusyError,
    WorkflowOwnershipLostError,
    WorkflowTransientError,
    safe_workflow_error_message,
)
from app.services.workflows.executor import execute_workflow
from app.services.workflows.factories import (
    build_diagnostic_service,
    build_work_order_proposal_service,
)

logger = logging.getLogger(__name__)

WORKFLOW_TASK_FAILED = "The workflow task failed."


class WorkflowAttemptError(Exception):
    """A failed attempt wrapper that preserves its execution claim."""

    def __init__(
        self,
        original: BaseException,
        *,
        claimed_started_at: datetime,
    ) -> None:
        super().__init__(str(original))
        self.original = original
        self.claimed_started_at = claimed_started_at


def _retry_countdown(retries: int) -> int:
    delay = settings.celery_task_retry_backoff_seconds * (2**retries)
    return min(delay, settings.celery_task_retry_backoff_max_seconds)


def _should_retry(exc: BaseException) -> bool:
    return isinstance(exc, WorkflowTransientError) or is_transient_error(exc)


def _claim_retry_after(started_at: datetime | None) -> int:
    if started_at is None:
        return 1
    remaining = (
        started_at
        + timedelta(seconds=workflow_execution_stale_after_seconds())
        - datetime.now(UTC)
    ).total_seconds()
    return max(1, int(remaining) + 1)


async def _release_claim_for_retry(
    background_task_id: uuid.UUID,
    claimed_started_at: datetime,
) -> bool:
    async with async_session_factory() as session:
        return await release_background_task_claim(
            session,
            background_task_id,
            claimed_started_at=claimed_started_at,
        )


async def run_workflow(
    workflow_run_id: uuid.UUID,
    background_task_id: uuid.UUID | None = None,
) -> str:
    claimed_started_at: datetime | None = None
    vector_index: DatabaseVectorIndex | None = None
    async with async_session_factory() as session:
        try:
            if background_task_id is not None:
                task = await session.get(BackgroundTask, background_task_id)
                if task is not None and task.status in (
                    BackgroundTaskStatus.SUCCEEDED,
                    BackgroundTaskStatus.CANCELLED,
                ):
                    logger.info(
                        "Skipping duplicate delivery for terminal background "
                        "task",
                        extra={
                            "event": "workflow_duplicate_skipped",
                            "workflow_run_id": str(workflow_run_id),
                            "background_task_id": str(background_task_id),
                            "background_task_status": task.status.value,
                        },
                    )
                    return str(workflow_run_id)

                workflow_run = await session.get(
                    WorkflowRun,
                    workflow_run_id,
                )
                if workflow_run is not None:
                    if workflow_run.status is WorkflowRunStatus.COMPLETED:
                        await mark_background_task_succeeded(
                            session,
                            background_task_id,
                        )
                        await session.commit()
                        return str(workflow_run_id)
                    if workflow_run.status is WorkflowRunStatus.FAILED:
                        await mark_background_task_failed(
                            session,
                            background_task_id,
                            workflow_run.error_message
                            or WORKFLOW_TASK_FAILED,
                        )
                        await session.commit()
                        return str(workflow_run_id)
                    if workflow_run.status is WorkflowRunStatus.PAUSED:
                        logger.info(
                            "Skipping duplicate delivery for paused workflow "
                            "run",
                            extra={
                                "event": "workflow_paused_skip",
                                "workflow_run_id": str(workflow_run_id),
                                "background_task_id": str(background_task_id),
                                "workflow_status": workflow_run.status.value,
                            },
                        )
                        return str(workflow_run_id)

                claimed_task = await claim_background_task_execution(
                    session,
                    background_task_id,
                )
                if claimed_task is None:
                    current_task = await session.get(
                        BackgroundTask,
                        background_task_id,
                        populate_existing=True,
                    )
                    if (
                        current_task is not None
                        and current_task.status
                        is BackgroundTaskStatus.RUNNING
                    ):
                        raise WorkflowExecutionBusyError(
                            _claim_retry_after(current_task.started_at)
                        )
                    return str(workflow_run_id)
                claimed_started_at = claimed_task.started_at
                if claimed_started_at is None:
                    raise WorkflowOwnershipLostError(
                        "The workflow execution claim was not recorded."
                    )

            vector_index = DatabaseVectorIndex(
                engine=engine,
                embedding_provider=get_embedding_provider(),
                owns_engine=False,
            )
            diagnostic_service = build_diagnostic_service()
            proposal_service = build_work_order_proposal_service(
                diagnostic_service=diagnostic_service,
            )
            workflow_run = await execute_workflow(
                session,
                workflow_run_id=workflow_run_id,
                vector_index=vector_index,
                diagnostic_service=diagnostic_service,
                proposal_service=proposal_service,
                background_task_id=background_task_id,
                claimed_started_at=claimed_started_at,
            )

            if (
                background_task_id is not None
                and claimed_started_at is not None
            ):
                marked = await mark_claimed_background_task_succeeded(
                    session,
                    background_task_id,
                    claimed_started_at=claimed_started_at,
                )
                if not marked:
                    await session.rollback()
                    logger.warning(
                        "Workflow completion lost its execution claim",
                        extra={
                            "event": "workflow_completion_claim_lost",
                            "workflow_run_id": str(workflow_run_id),
                            "background_task_id": str(background_task_id),
                        },
                    )
                    return str(workflow_run_id)

            await session.commit()
            return str(workflow_run.id)
        except WorkflowOwnershipLostError:
            await session.rollback()
            logger.warning(
                "Workflow execution claim was lost",
                extra={
                    "event": "workflow_execution_claim_lost",
                    "workflow_run_id": str(workflow_run_id),
                    "background_task_id": (
                        str(background_task_id)
                        if background_task_id is not None
                        else None
                    ),
                },
            )
            return str(workflow_run_id)
        except Exception as exc:
            if (
                claimed_started_at is not None
                and background_task_id is not None
            ):
                raise WorkflowAttemptError(
                    exc,
                    claimed_started_at=claimed_started_at,
                ) from exc
            raise
        finally:
            if vector_index is not None:
                await vector_index.close()


async def _finalize_failed_task(
    workflow_run_id: uuid.UUID,
    background_task_id: uuid.UUID | None,
    error: BaseException,
    *,
    claimed_started_at: datetime | None = None,
) -> None:
    message = safe_workflow_error_message(error)
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        workflow_run = await session.get(
            WorkflowRun,
            workflow_run_id,
            with_for_update=True,
            populate_existing=True,
        )
        task: BackgroundTask | None = None
        if background_task_id is not None:
            task = await session.get(
                BackgroundTask,
                background_task_id,
                with_for_update=True,
                populate_existing=True,
            )

        claim_owned = (
            claimed_started_at is not None
            and task is not None
            and task.status is BackgroundTaskStatus.RUNNING
            and task.started_at == claimed_started_at
        )
        unclaimed_pending = (
            claimed_started_at is None
            and (task is None or task.status is BackgroundTaskStatus.PENDING)
        )
        owns_claim = claim_owned or unclaimed_pending

        if task is not None:
            if (
                workflow_run is not None
                and workflow_run.status is WorkflowRunStatus.COMPLETED
            ):
                if task.status in (
                    BackgroundTaskStatus.PENDING,
                    BackgroundTaskStatus.RUNNING,
                ):
                    task.status = BackgroundTaskStatus.SUCCEEDED
                    task.finished_at = now
                    task.error_message = None
            elif (
                workflow_run is not None
                and workflow_run.status is WorkflowRunStatus.FAILED
            ):
                if task.status in (
                    BackgroundTaskStatus.PENDING,
                    BackgroundTaskStatus.RUNNING,
                ):
                    task.status = BackgroundTaskStatus.FAILED
                    task.finished_at = now
                    task.error_message = (
                        workflow_run.error_message or message
                    )[:2000]
            elif owns_claim and task.status in (
                BackgroundTaskStatus.PENDING,
                BackgroundTaskStatus.RUNNING,
            ):
                task.status = BackgroundTaskStatus.FAILED
                task.finished_at = now
                task.error_message = message[:2000]

        if (
            workflow_run is not None
            and workflow_run.status
            not in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED)
            and owns_claim
        ):
            workflow_run.status = WorkflowRunStatus.FAILED
            workflow_run.current_step = "failed"
            workflow_run.finished_at = now
            workflow_run.error_message = message[:2000]
        await session.commit()

    logger.error(
        "Workflow task failed",
        extra={
            "event": "workflow_task_failed",
            "workflow_run_id": str(workflow_run_id),
            "error_type": type(error).__name__,
        },
    )


def _handle_failed_attempt(
    task: Any,
    run_uuid: uuid.UUID,
    task_uuid: uuid.UUID | None,
    exc: BaseException,
    claimed_started_at: datetime | None,
) -> NoReturn:
    retries = task.request.retries
    unclaimed_failure = claimed_started_at is None and task_uuid is not None
    if (
        unclaimed_failure or _should_retry(exc)
    ) and retries < settings.celery_task_max_retries:
        if task_uuid is not None and claimed_started_at is not None:
            run_async_task(
                _release_claim_for_retry(
                    task_uuid,
                    claimed_started_at,
                ),
                engine=engine,
            )
        raise task.retry(
            exc=exc,
            countdown=_retry_countdown(retries),
        )
    run_async_task(
        _finalize_failed_task(
            run_uuid,
            task_uuid,
            exc,
            claimed_started_at=claimed_started_at,
        ),
        engine=engine,
    )
    raise exc


def _execute_task(
    task: Any,
    workflow_run_id: str,
    background_task_id: str | None,
) -> str:
    run_uuid = uuid.UUID(workflow_run_id)
    task_uuid = uuid.UUID(background_task_id) if background_task_id else None
    try:
        return run_async_task(
            run_workflow(run_uuid, task_uuid),
            engine=engine,
        )
    except WorkflowExecutionBusyError as exc:
        retries = task.request.retries
        if retries < settings.celery_task_max_retries:
            raise task.retry(
                exc=exc,
                countdown=exc.retry_after_seconds,
            )
        logger.warning(
            "Workflow execution remains owned by another worker",
            extra={
                "event": "workflow_execution_busy",
                "workflow_run_id": str(run_uuid),
                "background_task_id": (
                    str(task_uuid) if task_uuid is not None else None
                ),
            },
        )
        return str(run_uuid)
    except WorkflowAttemptError as wrapped:
        _handle_failed_attempt(
            task,
            run_uuid,
            task_uuid,
            wrapped.original,
            wrapped.claimed_started_at,
        )
    except Exception as exc:  # noqa: BLE001 - classify every task failure
        _handle_failed_attempt(task, run_uuid, task_uuid, exc, None)


@celery_app.task(
    bind=True,
    name=DIAGNOSTIC_INVESTIGATION_TASK_NAME,
    acks_late=True,
    track_started=True,
)
def run_diagnostic_investigation_task(
    self,
    workflow_run_id: str,
    background_task_id: str | None = None,
) -> str:
    return _execute_task(self, workflow_run_id, background_task_id)


@celery_app.task(
    bind=True,
    name=WORK_ORDER_PROPOSAL_TASK_NAME,
    acks_late=True,
    track_started=True,
)
def run_work_order_proposal_task(
    self,
    workflow_run_id: str,
    background_task_id: str | None = None,
) -> str:
    return _execute_task(self, workflow_run_id, background_task_id)


__all__ = [
    "run_diagnostic_investigation_task",
    "run_work_order_proposal_task",
    "run_workflow",
]
