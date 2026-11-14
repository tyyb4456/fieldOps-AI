from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_operations_user
from app.api.dependencies.diagnostics import get_diagnostic_service
from app.api.dependencies.vector_index import get_vector_index
from app.api.serializers import workflow_run_accepted_response
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.diagnostics.diagnostic import DiagnosticInvestigationRequest
from app.schemas.workflow_runs.workflow_run import WorkflowRunAcceptedResponse
from app.services.diagnostics.diagnostics import DiagnosticService
from app.services.rag.vector_index import VectorIndex
from app.services.workflows.scheduling import (
    enqueue_diagnostic_investigation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostics", tags=["Diagnostics"])


@router.post(
    "/investigate",
    response_model=WorkflowRunAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a technical diagnostic investigation",
)
async def investigate_complaint(
    payload: DiagnosticInvestigationRequest,
    user: User = Depends(require_operations_user),
    session: AsyncSession = Depends(get_db_session),
    vector_index: VectorIndex = Depends(get_vector_index),
    diagnostic_service: DiagnosticService = Depends(get_diagnostic_service),
) -> WorkflowRunAcceptedResponse:
    actor_id = user.id
    workflow_run = await enqueue_diagnostic_investigation(
        session,
        user=user,
        complaint_id=payload.complaint_id,
        focus=payload.focus,
        vector_index=vector_index,
        diagnostic_service=diagnostic_service,
    )
    logger.info(
        "Diagnostic investigation queued",
        extra={
            "event": "diagnostic_investigation_queued",
            "actor_id": str(actor_id),
            "complaint_id": str(payload.complaint_id),
            "workflow_run_id": str(workflow_run.id),
        },
    )
    return workflow_run_accepted_response(workflow_run)
