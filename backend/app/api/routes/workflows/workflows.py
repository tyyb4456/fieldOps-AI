from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_operations_user
from app.api.serializers import workflow_run_detail_response
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.workflow_runs.workflow_run import WorkflowRunDetailResponse
from app.services.diagnostics.diagnostics import (
    get_complaint_for_operations_user,
)
from app.services.workflow_runs import workflow_runs as workflow_run_service

router = APIRouter(prefix="/workflows", tags=["Workflows"])


@router.get(
    "/{workflow_run_id}",
    response_model=WorkflowRunDetailResponse,
    summary="Read an operations workflow run and its result",
)
async def read_workflow_run(
    workflow_run_id: uuid.UUID,
    user: User = Depends(require_operations_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunDetailResponse:
    workflow_run = await workflow_run_service.get_workflow_run(
        session,
        workflow_run_id,
    )
    await get_complaint_for_operations_user(
        session,
        user,
        workflow_run.complaint_id,
    )
    return workflow_run_detail_response(workflow_run)
