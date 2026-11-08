from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    get_current_user,
    require_admin_user,
    require_operations_user,
    require_technician_user,
)
from app.api.serializers import (
    assignment_response,
    work_order_response,
)
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.enums import Priority, WorkOrderStatus
from app.models.user import User
from app.schemas.assignment import AssignmentResponse
from app.schemas.work_order import (
    WorkOrderCreate,
    WorkOrderListResponse,
    WorkOrderResponse,
    WorkOrderStatusUpdate,
    WorkOrderUpdate,
)
from app.services import assignments as assignment_service
from app.services import work_orders as work_order_service
from app.services.assignments import (
    InvalidAssignmentStateError,
    is_active_assignment_conflict,
)
from app.services.work_orders import (
    InvalidComplaintConversionError,
    InvalidWorkOrderTransitionError,
    WorkOrderAlreadyExistsError,
    WorkOrderNotEditableError,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Work Orders"])


def _work_order_conflict_error() -> AppError:
    return AppError(
        "A work order already exists for this complaint.",
        status_code=status.HTTP_409_CONFLICT,
        code="work_order_conflict",
    )


def _invalid_complaint_state_error() -> AppError:
    return AppError(
        "Complaint is not eligible for work-order conversion.",
        status_code=status.HTTP_409_CONFLICT,
        code="invalid_complaint_state",
    )


def _invalid_transition_error() -> AppError:
    return AppError(
        "Work order cannot be changed in its current state.",
        status_code=status.HTTP_409_CONFLICT,
        code="invalid_status_transition",
    )


def _not_editable_error() -> AppError:
    return AppError(
        "Work-order fields are not editable in the current state.",
        status_code=status.HTTP_409_CONFLICT,
        code="work_order_not_editable",
    )


def _invalid_assignment_state_error() -> AppError:
    return AppError(
        "The assignment cannot be changed in its current state.",
        status_code=status.HTTP_409_CONFLICT,
        code="invalid_assignment_state",
    )


def _assignment_conflict_error() -> AppError:
    return AppError(
        "Work order already has an active assignment.",
        status_code=status.HTTP_409_CONFLICT,
        code="assignment_conflict",
    )


@router.get(
    "/work-orders",
    response_model=WorkOrderListResponse,
    summary="List work orders visible to the authenticated user",
)
@router.get(
    "/admin/work-orders",
    response_model=WorkOrderListResponse,
    summary="Admin: list all work orders",
)
async def list_work_orders(
    work_order_status: WorkOrderStatus | None = Query(
        default=None,
        alias="status",
    ),
    priority: Priority | None = Query(default=None),
    complaint_id: uuid.UUID | None = Query(default=None),
    equipment_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkOrderListResponse:
    items, total = await work_order_service.list_work_orders(
        session,
        current_user,
        status=work_order_status,
        priority=priority,
        complaint_id=complaint_id,
        equipment_id=equipment_id,
        limit=limit,
        offset=offset,
    )
    return WorkOrderListResponse(
        items=[work_order_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/work-orders/{work_order_id}",
    response_model=WorkOrderResponse,
    summary="Read a work order visible to the authenticated user",
)
@router.get(
    "/admin/work-orders/{work_order_id}",
    response_model=WorkOrderResponse,
    summary="Admin: read a work order",
)
async def read_work_order(
    work_order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkOrderResponse:
    work_order = await work_order_service.get_work_order(
        session,
        current_user,
        work_order_id,
    )
    return work_order_response(work_order)


@router.post(
    "/admin/complaints/{complaint_id}/work-orders",
    response_model=WorkOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: convert an eligible complaint into a work order",
)
async def create_work_order(
    complaint_id: uuid.UUID,
    payload: WorkOrderCreate,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkOrderResponse:
    try:
        work_order = await work_order_service.create_work_order_from_complaint(
            session,
            complaint_id=complaint_id,
            data=payload,
            actor_id=admin.id,
        )
        await session.commit()
    except WorkOrderAlreadyExistsError as exc:
        await session.rollback()
        raise _work_order_conflict_error() from exc
    except InvalidComplaintConversionError as exc:
        await session.rollback()
        raise _invalid_complaint_state_error() from exc
    except IntegrityError as exc:
        await session.rollback()
        raise _work_order_conflict_error() from exc

    await session.refresh(work_order)
    logger.info(
        "Work order created",
        extra={
            "event": "work_order_created",
            "actor_id": str(admin.id),
            "complaint_id": str(work_order.complaint_id),
            "work_order_id": str(work_order.id),
        },
    )
    return work_order_response(work_order)


@router.patch(
    "/admin/work-orders/{work_order_id}",
    response_model=WorkOrderResponse,
    summary="Admin: update editable work-order fields",
)
async def update_work_order(
    work_order_id: uuid.UUID,
    payload: WorkOrderUpdate,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkOrderResponse:
    work_order = await work_order_service.get_work_order(
        session,
        admin,
        work_order_id,
        for_update=True,
    )
    try:
        updated = await work_order_service.update_work_order(
            session,
            work_order,
            payload,
        )
        await session.commit()
    except WorkOrderNotEditableError as exc:
        await session.rollback()
        raise _not_editable_error() from exc

    await session.refresh(updated)
    logger.info(
        "Work order updated",
        extra={
            "event": "work_order_updated",
            "actor_id": str(admin.id),
            "work_order_id": str(updated.id),
        },
    )
    return work_order_response(updated)


@router.post(
    "/work-orders/{work_order_id}/status",
    response_model=WorkOrderResponse,
    summary="Update work-order status within the permitted lifecycle",
)
@router.post(
    "/admin/work-orders/{work_order_id}/status",
    response_model=WorkOrderResponse,
    summary="Admin: update work-order status",
)
async def update_work_order_status(
    work_order_id: uuid.UUID,
    payload: WorkOrderStatusUpdate,
    current_user: User = Depends(require_operations_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkOrderResponse:
    try:
        work_order = await work_order_service.transition_work_order(
            session,
            user=current_user,
            work_order_id=work_order_id,
            target_status=payload.status,
        )
        await session.commit()
    except InvalidWorkOrderTransitionError as exc:
        await session.rollback()
        raise _invalid_transition_error() from exc

    await session.refresh(work_order)
    logger.info(
        "Work order status changed",
        extra={
            "event": "work_order_status_changed",
            "actor_id": str(current_user.id),
            "work_order_id": str(work_order.id),
            "status_to": work_order.status.value,
        },
    )
    return work_order_response(work_order)


@router.post(
    "/work-orders/{work_order_id}/accept",
    response_model=AssignmentResponse,
    summary="Technician: accept the offered work order",
)
async def accept_work_order(
    work_order_id: uuid.UUID,
    technician_user: User = Depends(require_technician_user),
    session: AsyncSession = Depends(get_db_session),
) -> AssignmentResponse:
    try:
        assignment = await assignment_service.accept_work_order_offer(
            session,
            user=technician_user,
            work_order_id=work_order_id,
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
        "Work order offer accepted",
        extra={
            "event": "assignment_accepted",
            "actor_id": str(technician_user.id),
            "work_order_id": str(assignment.work_order_id),
            "assignment_id": str(assignment.id),
        },
    )
    return assignment_response(assignment)


@router.post(
    "/work-orders/{work_order_id}/reject",
    response_model=AssignmentResponse,
    summary="Technician: reject the offered work order",
)
async def reject_work_order(
    work_order_id: uuid.UUID,
    technician_user: User = Depends(require_technician_user),
    session: AsyncSession = Depends(get_db_session),
) -> AssignmentResponse:
    try:
        assignment = await assignment_service.reject_work_order_offer(
            session,
            user=technician_user,
            work_order_id=work_order_id,
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
        "Work order offer rejected",
        extra={
            "event": "assignment_rejected",
            "actor_id": str(technician_user.id),
            "work_order_id": str(assignment.work_order_id),
            "assignment_id": str(assignment.id),
        },
    )
    return assignment_response(assignment)
