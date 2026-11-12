from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    require_admin_user,
    require_operations_user,
    require_technician_user,
)
from app.api.serializers import (
    assignment_response,
    technician_summary_response,
)
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.enums import AssignmentStatus
from app.models.user import User
from app.schemas.assignments.assignment import (
    AssignmentCreate,
    AssignmentListResponse,
    AssignmentResponse,
    TechnicianListResponse,
)
from app.services.assignments import assignments as assignment_service
from app.services.assignments.assignments import (
    AssignmentConflictError,
    InvalidAssignmentStateError,
    TechnicianNotEligibleError,
    is_active_assignment_conflict,
)
from app.services.work_orders import work_orders as work_order_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Assignments"])


def _assignment_conflict_error() -> AppError:
    return AppError(
        "Work order already has an active assignment.",
        status_code=status.HTTP_409_CONFLICT,
        code="assignment_conflict",
    )


def _invalid_assignment_state_error() -> AppError:
    return AppError(
        "The assignment cannot be changed in its current state.",
        status_code=status.HTTP_409_CONFLICT,
        code="invalid_assignment_state",
    )


def _technician_not_eligible_error() -> AppError:
    return AppError(
        "The selected technician is not eligible for assignment.",
        status_code=status.HTTP_409_CONFLICT,
        code="technician_not_eligible",
    )


@router.get(
    "/assignments",
    response_model=AssignmentListResponse,
    summary="List assignments visible to the authenticated user",
)
@router.get(
    "/admin/assignments",
    response_model=AssignmentListResponse,
    summary="Admin: list all assignments",
)
async def list_assignments(
    assignment_status: AssignmentStatus | None = Query(
        default=None,
        alias="status",
    ),
    work_order_id: uuid.UUID | None = Query(default=None),
    technician_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_operations_user),
    session: AsyncSession = Depends(get_db_session),
) -> AssignmentListResponse:
    items, total = await assignment_service.list_assignments(
        session,
        current_user,
        status=assignment_status,
        work_order_id=work_order_id,
        technician_id=technician_id,
        limit=limit,
        offset=offset,
    )
    return AssignmentListResponse(
        items=[assignment_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/work-orders/{work_order_id}/assignments",
    response_model=AssignmentListResponse,
    summary="Admin: list a work order's assignment history",
)
async def list_work_order_assignments(
    work_order_id: uuid.UUID,
    assignment_status: AssignmentStatus | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> AssignmentListResponse:
    await work_order_service.get_work_order(
        session,
        admin,
        work_order_id,
    )
    items, total = await assignment_service.list_assignments(
        session,
        admin,
        status=assignment_status,
        work_order_id=work_order_id,
        technician_id=None,
        limit=limit,
        offset=offset,
    )
    return AssignmentListResponse(
        items=[assignment_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/assignments/{assignment_id}",
    response_model=AssignmentResponse,
    summary="Read an assignment visible to the authenticated user",
)
@router.get(
    "/admin/assignments/{assignment_id}",
    response_model=AssignmentResponse,
    summary="Admin: read an assignment",
)
async def read_assignment(
    assignment_id: uuid.UUID,
    current_user: User = Depends(require_operations_user),
    session: AsyncSession = Depends(get_db_session),
) -> AssignmentResponse:
    assignment = await assignment_service.get_assignment(
        session,
        current_user,
        assignment_id,
    )
    return assignment_response(assignment)


@router.post(
    "/admin/work-orders/{work_order_id}/assignments",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: offer a work order to an eligible technician",
)
async def create_assignment(
    work_order_id: uuid.UUID,
    payload: AssignmentCreate,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> AssignmentResponse:
    try:
        assignment = await assignment_service.create_assignment(
            session,
            work_order_id=work_order_id,
            technician_id=payload.technician_id,
            reassign=False,
        )
        await session.commit()
    except AssignmentConflictError as exc:
        await session.rollback()
        raise _assignment_conflict_error() from exc
    except InvalidAssignmentStateError as exc:
        await session.rollback()
        raise _invalid_assignment_state_error() from exc
    except TechnicianNotEligibleError as exc:
        await session.rollback()
        raise _technician_not_eligible_error() from exc
    except IntegrityError as exc:
        await session.rollback()
        if not is_active_assignment_conflict(exc):
            raise
        raise _assignment_conflict_error() from exc

    await session.refresh(assignment)
    logger.info(
        "Technician assigned",
        extra={
            "event": "assignment_created",
            "actor_id": str(admin.id),
            "work_order_id": str(assignment.work_order_id),
            "technician_id": str(assignment.technician_id),
            "assignment_id": str(assignment.id),
        },
    )
    return assignment_response(assignment)


@router.post(
    "/admin/work-orders/{work_order_id}/assignments/reassign",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: reassign a work order by withdrawing active offers",
)
@router.post(
    "/admin/work-orders/{work_order_id}/reassign",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: reassign a work order",
    include_in_schema=False,
)
async def reassign_work_order(
    work_order_id: uuid.UUID,
    payload: AssignmentCreate,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> AssignmentResponse:
    try:
        assignment = await assignment_service.create_assignment(
            session,
            work_order_id=work_order_id,
            technician_id=payload.technician_id,
            reassign=True,
        )
        await session.commit()
    except InvalidAssignmentStateError as exc:
        await session.rollback()
        raise _invalid_assignment_state_error() from exc
    except TechnicianNotEligibleError as exc:
        await session.rollback()
        raise _technician_not_eligible_error() from exc
    except IntegrityError as exc:
        await session.rollback()
        if not is_active_assignment_conflict(exc):
            raise
        raise _assignment_conflict_error() from exc

    await session.refresh(assignment)
    logger.info(
        "Technician reassigned",
        extra={
            "event": "assignment_reassigned",
            "actor_id": str(admin.id),
            "work_order_id": str(assignment.work_order_id),
            "technician_id": str(assignment.technician_id),
            "assignment_id": str(assignment.id),
        },
    )
    return assignment_response(assignment)


@router.post(
    "/assignments/{assignment_id}/accept",
    response_model=AssignmentResponse,
    summary="Technician: accept an offered assignment",
)
async def accept_assignment(
    assignment_id: uuid.UUID,
    technician_user: User = Depends(require_technician_user),
    session: AsyncSession = Depends(get_db_session),
) -> AssignmentResponse:
    try:
        assignment = await assignment_service.accept_assignment(
            session,
            user=technician_user,
            assignment_id=assignment_id,
        )
        await session.commit()
    except InvalidAssignmentStateError as exc:
        await session.rollback()
        raise _invalid_assignment_state_error() from exc
    except IntegrityError as exc:
        await session.rollback()
        if not is_active_assignment_conflict(exc):
            raise
        raise _assignment_conflict_error() from exc

    await session.refresh(assignment)
    logger.info(
        "Assignment accepted",
        extra={
            "event": "assignment_accepted",
            "actor_id": str(technician_user.id),
            "work_order_id": str(assignment.work_order_id),
            "assignment_id": str(assignment.id),
        },
    )
    return assignment_response(assignment)


@router.post(
    "/assignments/{assignment_id}/reject",
    response_model=AssignmentResponse,
    summary="Technician: reject an offered assignment",
)
async def reject_assignment(
    assignment_id: uuid.UUID,
    technician_user: User = Depends(require_technician_user),
    session: AsyncSession = Depends(get_db_session),
) -> AssignmentResponse:
    try:
        assignment = await assignment_service.reject_assignment(
            session,
            user=technician_user,
            assignment_id=assignment_id,
        )
        await session.commit()
    except InvalidAssignmentStateError as exc:
        await session.rollback()
        raise _invalid_assignment_state_error() from exc
    except IntegrityError as exc:
        await session.rollback()
        if not is_active_assignment_conflict(exc):
            raise
        raise _assignment_conflict_error() from exc

    await session.refresh(assignment)
    logger.info(
        "Assignment rejected",
        extra={
            "event": "assignment_rejected",
            "actor_id": str(technician_user.id),
            "work_order_id": str(assignment.work_order_id),
            "assignment_id": str(assignment.id),
        },
    )
    return assignment_response(assignment)


@router.post(
    "/admin/assignments/{assignment_id}/withdraw",
    response_model=AssignmentResponse,
    summary="Admin: withdraw an active assignment",
)
async def withdraw_assignment(
    assignment_id: uuid.UUID,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> AssignmentResponse:
    try:
        assignment = await assignment_service.withdraw_assignment(
            session,
            user=admin,
            assignment_id=assignment_id,
        )
        await session.commit()
    except InvalidAssignmentStateError as exc:
        await session.rollback()
        raise _invalid_assignment_state_error() from exc
    except IntegrityError as exc:
        await session.rollback()
        if not is_active_assignment_conflict(exc):
            raise
        raise _assignment_conflict_error() from exc

    await session.refresh(assignment)
    logger.info(
        "Assignment withdrawn",
        extra={
            "event": "assignment_withdrawn",
            "actor_id": str(admin.id),
            "work_order_id": str(assignment.work_order_id),
            "assignment_id": str(assignment.id),
        },
    )
    return assignment_response(assignment)


@router.get(
    "/technicians",
    response_model=TechnicianListResponse,
    summary="Admin: list eligible technicians",
)
@router.get(
    "/admin/technicians",
    response_model=TechnicianListResponse,
    summary="Admin: list eligible technicians",
    include_in_schema=False,
)
async def list_technicians(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> TechnicianListResponse:
    items, total = await work_order_service.list_eligible_technicians(
        session,
        limit=limit,
        offset=offset,
    )
    return TechnicianListResponse(
        items=[
            technician_summary_response(item)
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
