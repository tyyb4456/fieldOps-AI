from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    require_admin_user,
    require_operations_user,
)
from app.api.dependencies.vector_index import get_vector_index
from app.api.dependencies.work_order_proposals import (
    get_work_order_proposal_service,
)
from app.api.serializers import work_order_proposal_response
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.enums import WorkOrderProposalStatus
from app.models.user import User
from app.schemas.work_orders.work_order_proposal import (
    WorkOrderProposalApproveRequest,
    WorkOrderProposalListResponse,
    WorkOrderProposalRejectRequest,
    WorkOrderProposalResponse,
)
from app.services.assignments.assignments import is_active_assignment_conflict
from app.services.diagnostics.diagnostics import (
    DiagnosticAgentUnavailableError,
    DiagnosticRetrievalUnavailableError,
)
from app.services.rag.vector_index import VectorIndex
from app.services.work_orders.work_order_proposals import (
    InvalidProposalStateError,
    ProposalAgentUnavailableError,
    ProposalAlreadyConvertedError,
    ProposalAlreadyPendingError,
    ProposalGenerationError,
    ProposalNotEligibleError,
    ProposalStaleError,
    ProposalTechnicianNotEligibleError,
    WorkOrderProposalService,
    is_pending_proposal_conflict,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Work Order Proposals"])


def _proposal_not_eligible_error() -> AppError:
    return AppError(
        "Complaint is not eligible for work-order preparation.",
        status_code=status.HTTP_409_CONFLICT,
        code="complaint_not_eligible",
    )


def _proposal_pending_error() -> AppError:
    return AppError(
        "A work-order proposal is already pending review.",
        status_code=status.HTTP_409_CONFLICT,
        code="proposal_already_pending",
    )


def _proposal_conflict_error() -> AppError:
    return AppError(
        "The work-order proposal conflicts with existing records.",
        status_code=status.HTTP_409_CONFLICT,
        code="proposal_conflict",
    )


def _invalid_proposal_state_error() -> AppError:
    return AppError(
        "The work-order proposal cannot be changed in its current state.",
        status_code=status.HTTP_409_CONFLICT,
        code="invalid_proposal_state",
    )


def _proposal_stale_error() -> AppError:
    return AppError(
        "The work-order proposal is stale; generate a new proposal.",
        status_code=status.HTTP_409_CONFLICT,
        code="proposal_stale",
    )


def _technician_not_eligible_error() -> AppError:
    return AppError(
        "The selected technician is not eligible for assignment.",
        status_code=status.HTTP_409_CONFLICT,
        code="technician_not_eligible",
    )


def _proposal_agent_unavailable_error() -> AppError:
    return AppError(
        "The work-order preparation agent is unavailable.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="proposal_agent_unavailable",
    )


def _proposal_generation_error() -> AppError:
    return AppError(
        "The work-order proposal did not pass validation.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="proposal_generation_failed",
    )


def _retrieval_unavailable_error() -> AppError:
    return AppError(
        "Knowledge base search is unavailable.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="retrieval_unavailable",
    )


def _diagnostic_agent_unavailable_error() -> AppError:
    return AppError(
        "The diagnostic agent is unavailable.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="diagnostic_agent_unavailable",
    )


@router.post(
    "/admin/complaints/{complaint_id}/work-order-proposals",
    response_model=WorkOrderProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: prepare a reviewable work-order proposal",
)
async def generate_work_order_proposal(
    complaint_id: uuid.UUID,
    current_user: User = Depends(require_operations_user),
    session: AsyncSession = Depends(get_db_session),
    vector_index: VectorIndex = Depends(get_vector_index),
    proposal_service: WorkOrderProposalService = Depends(
        get_work_order_proposal_service
    ),
) -> WorkOrderProposalResponse:
    try:
        proposal = await proposal_service.generate(
            session=session,
            user=current_user,
            vector_index=vector_index,
            complaint_id=complaint_id,
        )
        await session.commit()
    except ProposalNotEligibleError as exc:
        await session.rollback()
        raise _proposal_not_eligible_error() from exc
    except ProposalAlreadyPendingError as exc:
        await session.rollback()
        raise _proposal_pending_error() from exc
    except ProposalAlreadyConvertedError as exc:
        await session.rollback()
        raise _proposal_conflict_error() from exc
    except ProposalStaleError as exc:
        await session.rollback()
        raise _proposal_stale_error() from exc
    except ProposalAgentUnavailableError as exc:
        await session.rollback()
        raise _proposal_agent_unavailable_error() from exc
    except ProposalGenerationError as exc:
        await session.rollback()
        raise _proposal_generation_error() from exc
    except DiagnosticRetrievalUnavailableError as exc:
        await session.rollback()
        raise _retrieval_unavailable_error() from exc
    except DiagnosticAgentUnavailableError as exc:
        await session.rollback()
        raise _diagnostic_agent_unavailable_error() from exc
    except IntegrityError as exc:
        await session.rollback()
        if not is_pending_proposal_conflict(exc):
            raise
        raise _proposal_pending_error() from exc

    await session.refresh(proposal)
    logger.info(
        "Work-order proposal generated",
        extra={
            "event": "work_order_proposal_generated",
            "actor_id": str(current_user.id),
            "complaint_id": str(proposal.complaint_id),
            "proposal_id": str(proposal.id),
        },
    )
    return work_order_proposal_response(proposal)


@router.get(
    "/admin/work-order-proposals",
    response_model=WorkOrderProposalListResponse,
    summary="Admin: list work-order proposals",
)
async def list_work_order_proposals(
    proposal_status: WorkOrderProposalStatus | None = Query(
        default=None,
        alias="status",
    ),
    complaint_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
    proposal_service: WorkOrderProposalService = Depends(
        get_work_order_proposal_service
    ),
) -> WorkOrderProposalListResponse:
    items, total = await proposal_service.list_proposals(
        session,
        admin,
        status=proposal_status,
        complaint_id=complaint_id,
        limit=limit,
        offset=offset,
    )
    return WorkOrderProposalListResponse(
        items=[work_order_proposal_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/work-order-proposals/{proposal_id}",
    response_model=WorkOrderProposalResponse,
    summary="Admin: read a work-order proposal",
)
async def read_work_order_proposal(
    proposal_id: uuid.UUID,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
    proposal_service: WorkOrderProposalService = Depends(
        get_work_order_proposal_service
    ),
) -> WorkOrderProposalResponse:
    proposal = await proposal_service.get(session, admin, proposal_id)
    return work_order_proposal_response(proposal)


@router.post(
    "/admin/work-order-proposals/{proposal_id}/approve",
    response_model=WorkOrderProposalResponse,
    summary="Admin: approve a proposal and execute conversion",
)
async def approve_work_order_proposal(
    proposal_id: uuid.UUID,
    payload: WorkOrderProposalApproveRequest,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
    proposal_service: WorkOrderProposalService = Depends(
        get_work_order_proposal_service
    ),
) -> WorkOrderProposalResponse:
    try:
        proposal = await proposal_service.approve(
            session=session,
            admin=admin,
            proposal_id=proposal_id,
            technician_id=payload.technician_id,
        )
        await session.commit()
    except InvalidProposalStateError as exc:
        await session.rollback()
        raise _invalid_proposal_state_error() from exc
    except ProposalStaleError as exc:
        await session.rollback()
        raise _proposal_stale_error() from exc
    except ProposalTechnicianNotEligibleError as exc:
        await session.rollback()
        raise _technician_not_eligible_error() from exc
    except IntegrityError as exc:
        await session.rollback()
        if not (
            is_active_assignment_conflict(exc)
            or is_pending_proposal_conflict(exc)
        ):
            raise
        raise _proposal_conflict_error() from exc

    await session.refresh(proposal)
    logger.info(
        "Work-order proposal approved",
        extra={
            "event": "work_order_proposal_approved",
            "actor_id": str(admin.id),
            "proposal_id": str(proposal.id),
            "complaint_id": str(proposal.complaint_id),
            "work_order_id": (
                str(proposal.resulting_work_order_id)
                if proposal.resulting_work_order_id is not None
                else None
            ),
            "assignment_id": (
                str(proposal.resulting_assignment_id)
                if proposal.resulting_assignment_id is not None
                else None
            ),
        },
    )
    return work_order_proposal_response(proposal)


@router.post(
    "/admin/work-order-proposals/{proposal_id}/reject",
    response_model=WorkOrderProposalResponse,
    summary="Admin: reject a pending proposal",
)
async def reject_work_order_proposal(
    proposal_id: uuid.UUID,
    payload: WorkOrderProposalRejectRequest,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
    proposal_service: WorkOrderProposalService = Depends(
        get_work_order_proposal_service
    ),
) -> WorkOrderProposalResponse:
    try:
        proposal = await proposal_service.reject(
            session=session,
            admin=admin,
            proposal_id=proposal_id,
            reason=payload.reason,
        )
        await session.commit()
    except InvalidProposalStateError as exc:
        await session.rollback()
        raise _invalid_proposal_state_error() from exc

    await session.refresh(proposal)
    logger.info(
        "Work-order proposal rejected",
        extra={
            "event": "work_order_proposal_rejected",
            "actor_id": str(admin.id),
            "proposal_id": str(proposal.id),
            "complaint_id": str(proposal.complaint_id),
        },
    )
    return work_order_proposal_response(proposal)
