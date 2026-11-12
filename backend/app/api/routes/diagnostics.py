from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_operations_user
from app.api.dependencies.diagnostics import get_diagnostic_service
from app.api.dependencies.vector_index import get_vector_index
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.diagnostic import (
    DiagnosticCauseResponse,
    DiagnosticCheckResponse,
    DiagnosticInvestigationRequest,
    DiagnosticInvestigationResponse,
)
from app.schemas.knowledge_answer import CitationResponse
from app.services.diagnostics import (
    DiagnosticAgentUnavailableError,
    DiagnosticRetrievalUnavailableError,
    DiagnosticService,
)
from app.services.vector_index import VectorIndex

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostics", tags=["Diagnostics"])

DIAGNOSTIC_DISCLAIMER = (
    "This is an AI-generated diagnostic recommendation. It must be verified by "
    "a qualified technician and does not replace approved service procedures or "
    "on-site inspection."
)


@router.post(
    "/investigate",
    response_model=DiagnosticInvestigationResponse,
    summary="Investigate a complaint with the technical diagnostic agent",
)
async def investigate_complaint(
    payload: DiagnosticInvestigationRequest,
    user: User = Depends(require_operations_user),
    session: AsyncSession = Depends(get_db_session),
    vector_index: VectorIndex = Depends(get_vector_index),
    diagnostic_service: DiagnosticService = Depends(get_diagnostic_service),
) -> DiagnosticInvestigationResponse:
    try:
        result = await diagnostic_service.investigate(
            session=session,
            user=user,
            vector_index=vector_index,
            complaint_id=payload.complaint_id,
            focus=payload.focus,
        )
    except DiagnosticRetrievalUnavailableError as exc:
        logger.warning(
            "Diagnostic retrieval unavailable",
            extra={"event": "diagnostic_retrieval_unavailable"},
        )
        raise AppError(
            "Knowledge base search is unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="retrieval_unavailable",
        ) from exc
    except DiagnosticAgentUnavailableError as exc:
        logger.warning(
            "Diagnostic agent unavailable",
            extra={"event": "diagnostic_agent_unavailable"},
        )
        raise AppError(
            "The diagnostic agent is unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="diagnostic_agent_unavailable",
        ) from exc

    return DiagnosticInvestigationResponse(
        complaint_id=result.complaint_id,
        status=result.status,
        summary=result.summary,
        probable_causes=[
            DiagnosticCauseResponse(
                cause=cause.cause,
                basis=cause.basis,
                evidence_chunk_ids=list(cause.evidence_chunk_ids),
            )
            for cause in result.probable_causes
        ],
        recommended_checks=[
            DiagnosticCheckResponse(
                step=check.step,
                safety_note=check.safety_note,
                evidence_chunk_ids=list(check.evidence_chunk_ids),
            )
            for check in result.recommended_checks
        ],
        missing_information=list(result.missing_information),
        safety_warnings=list(result.safety_warnings),
        conflicting_evidence_notes=list(result.conflicting_evidence_notes),
        requires_escalation=result.requires_escalation,
        escalation_reason=result.escalation_reason,
        citations=[
            CitationResponse(
                source_id=citation.source_id,
                chunk_id=citation.chunk_id,
                document_id=citation.document_id,
                document_name=citation.document_name,
                manufacturer=citation.manufacturer,
                model=citation.model,
                version=citation.version,
                page_number=citation.page_number,
                chunk_index=citation.chunk_index,
                excerpt=citation.excerpt,
            )
            for citation in result.citations
        ],
        warnings=list(result.warnings),
        disclaimer=DIAGNOSTIC_DISCLAIMER,
    )
