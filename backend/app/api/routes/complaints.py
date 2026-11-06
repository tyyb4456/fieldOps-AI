from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    get_current_customer,
    require_customer_user,
)
from app.api.serializers import complaint_response
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.complaint import Complaint
from app.models.customer import Customer
from app.models.enums import ComplaintChannel, ComplaintStatus
from app.models.user import User
from app.schemas.complaint import (
    ComplaintCreate,
    ComplaintListResponse,
    ComplaintResponse,
    ComplaintUpdate,
)
from app.services import complaints as complaint_service
from app.services.complaints import InvalidComplaintTransitionError

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/customers/me/complaints",
    tags=["Complaints"],
)


def _complaint_conflict_error() -> AppError:
    return AppError(
        "Complaint conflicts with an existing record.",
        status_code=status.HTTP_409_CONFLICT,
        code="complaint_conflict",
    )


def _invalid_transition_error() -> AppError:
    return AppError(
        "Complaint cannot be changed in its current state.",
        status_code=status.HTTP_409_CONFLICT,
        code="invalid_status_transition",
    )


@router.get(
    "",
    response_model=ComplaintListResponse,
    summary="List the authenticated customer's complaints",
)
async def list_own_complaints(
    complaint_status: ComplaintStatus | None = Query(
        default=None,
        alias="status",
    ),
    equipment_id: uuid.UUID | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ComplaintListResponse:
    items, total = await complaint_service.list_complaints(
        session,
        customer_id=customer.id,
        status=complaint_status,
        equipment_id=equipment_id,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
    return ComplaintListResponse(
        items=[complaint_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=ComplaintResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a complaint for the authenticated customer",
)
async def create_own_complaint(
    payload: ComplaintCreate,
    current_user: User = Depends(require_customer_user),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ComplaintResponse:
    payload = payload.model_copy(update={"channel": ComplaintChannel.WEB})
    try:
        complaint = await complaint_service.create_complaint(
            session,
            customer=customer,
            data=payload,
            actor_id=current_user.id,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _complaint_conflict_error() from exc

    await session.refresh(complaint)
    logger.info(
        "Complaint created",
        extra={
            "event": "complaint_created",
            "actor_id": str(current_user.id),
            "customer_id": str(customer.id),
            "complaint_id": str(complaint.id),
            "equipment_id": (
                str(complaint.equipment_id)
                if complaint.equipment_id is not None
                else None
            ),
        },
    )
    return complaint_response(complaint)


@router.get(
    "/{complaint_id}",
    response_model=ComplaintResponse,
    summary="Retrieve one of the authenticated customer's complaints",
)
async def read_own_complaint(
    complaint_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ComplaintResponse:
    complaint = await complaint_service.get_complaint(
        session,
        complaint_id,
        customer_id=customer.id,
    )
    return complaint_response(complaint)


@router.patch(
    "/{complaint_id}",
    response_model=ComplaintResponse,
    summary="Update permitted fields of the customer's complaint",
)
async def update_own_complaint(
    complaint_id: uuid.UUID,
    payload: ComplaintUpdate,
    current_user: User = Depends(require_customer_user),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ComplaintResponse:
    complaint = await complaint_service.get_complaint(
        session,
        complaint_id,
        customer_id=customer.id,
        for_update=True,
    )
    try:
        updated = await complaint_service.update_complaint(
            session,
            complaint,
            payload,
            actor_id=current_user.id,
        )
        await session.commit()
    except InvalidComplaintTransitionError as exc:
        await session.rollback()
        raise _invalid_transition_error() from exc

    await session.refresh(updated)
    logger.info(
        "Complaint updated",
        extra={
            "event": "complaint_updated",
            "actor_id": str(current_user.id),
            "customer_id": str(customer.id),
            "complaint_id": str(updated.id),
        },
    )
    return complaint_response(updated)


@router.post(
    "/{complaint_id}/cancel",
    response_model=ComplaintResponse,
    summary="Cancel the customer's complaint when its state permits it",
)
async def cancel_own_complaint(
    complaint_id: uuid.UUID,
    current_user: User = Depends(require_customer_user),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> ComplaintResponse:
    complaint = await complaint_service.get_complaint(
        session,
        complaint_id,
        customer_id=customer.id,
        for_update=True,
    )
    previous_status = complaint.status
    try:
        cancelled = await complaint_service.cancel_complaint(
            session,
            complaint,
            actor_id=current_user.id,
        )
        await session.commit()
    except InvalidComplaintTransitionError as exc:
        await session.rollback()
        raise _invalid_transition_error() from exc

    await session.refresh(cancelled)
    logger.info(
        "Complaint cancelled",
        extra={
            "event": "complaint_cancelled",
            "actor_id": str(current_user.id),
            "customer_id": str(customer.id),
            "complaint_id": str(cancelled.id),
            "status_from": previous_status.value,
            "status_to": cancelled.status.value,
        },
    )
    return complaint_response(cancelled)
