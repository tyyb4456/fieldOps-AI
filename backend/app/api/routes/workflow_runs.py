from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_admin_user
from app.api.serializers import workflow_run_response
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.enums import WorkflowRunStatus
from app.models.user import User
from app.schemas.workflow_run import (
    WorkflowRunCreate,
    WorkflowRunListResponse,
    WorkflowRunResponse,
    WorkflowRunStatusUpdate,
)
from app.services import complaints as complaint_service
from app.services import workflow_runs as workflow_run_service
from app.services.workflow_runs import WorkflowRunStateError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Workflow Runs"])


def _invalid_workflow_run_state_error() -> AppError:
    return AppError(
        "Workflow run cannot be changed in its current state.",
        status_code=status.HTTP_409_CONFLICT,
        code="invalid_workflow_run_state",
    )


@router.get(
    "/workflow-runs",
    response_model=WorkflowRunListResponse,
    summary="Admin: list workflow-run history",
)
async def list_workflow_runs(
    complaint_id: uuid.UUID | None = Query(default=None),
    workflow_status: WorkflowRunStatus | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunListResponse:
    items, total = await workflow_run_service.list_workflow_runs(
        session,
        complaint_id=complaint_id,
        status=workflow_status,
        limit=limit,
        offset=offset,
    )
    return WorkflowRunListResponse(
        items=[workflow_run_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/workflow-runs/{workflow_run_id}",
    response_model=WorkflowRunResponse,
    summary="Admin: read a workflow run",
)
async def read_workflow_run(
    workflow_run_id: uuid.UUID,
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunResponse:
    workflow_run = await workflow_run_service.get_workflow_run(
        session,
        workflow_run_id,
    )
    return workflow_run_response(workflow_run)


@router.get(
    "/complaints/{complaint_id}/workflow-runs",
    response_model=WorkflowRunListResponse,
    summary="Admin: list a complaint's workflow-run history",
)
async def list_complaint_workflow_runs(
    complaint_id: uuid.UUID,
    workflow_status: WorkflowRunStatus | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunListResponse:
    await complaint_service.get_complaint(session, complaint_id)
    items, total = await workflow_run_service.list_workflow_runs(
        session,
        complaint_id=complaint_id,
        status=workflow_status,
        limit=limit,
        offset=offset,
    )
    return WorkflowRunListResponse(
        items=[workflow_run_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/complaints/{complaint_id}/workflow-runs",
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: register a running workflow run",
)
async def create_workflow_run(
    complaint_id: uuid.UUID,
    payload: WorkflowRunCreate,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunResponse:
    workflow_run = await workflow_run_service.create_workflow_run(
        session,
        complaint_id=complaint_id,
        data=payload,
    )
    await session.commit()
    await session.refresh(workflow_run)

    logger.info(
        "Workflow run created",
        extra={
            "event": "workflow_run_created",
            "actor_id": str(admin.id),
            "complaint_id": str(workflow_run.complaint_id),
            "workflow_run_id": str(workflow_run.id),
        },
    )
    return workflow_run_response(workflow_run)


@router.post(
    "/workflow-runs/{workflow_run_id}/status",
    response_model=WorkflowRunResponse,
    summary="Admin: apply a workflow-run lifecycle transition",
)
async def update_workflow_run_status(
    workflow_run_id: uuid.UUID,
    payload: WorkflowRunStatusUpdate,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunResponse:
    try:
        workflow_run = (
            await workflow_run_service.transition_workflow_run(
                session,
                workflow_run_id=workflow_run_id,
                data=payload,
            )
        )
        await session.commit()
    except WorkflowRunStateError as exc:
        await session.rollback()
        raise _invalid_workflow_run_state_error() from exc

    await session.refresh(workflow_run)
    logger.info(
        "Workflow run status changed",
        extra={
            "event": "workflow_run_status_changed",
            "actor_id": str(admin.id),
            "workflow_run_id": str(workflow_run.id),
            "status_to": workflow_run.status.value,
        },
    )
    return workflow_run_response(workflow_run)
