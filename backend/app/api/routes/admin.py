from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_admin_user
from app.api.serializers import (
    complaint_history_response,
    complaint_response,
    customer_profile_response,
    equipment_response,
)
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.enums import ComplaintStatus
from app.models.user import User
from app.schemas.complaints.complaint import (
    ComplaintHistoryListResponse,
    ComplaintListResponse,
    ComplaintResponse,
)
from app.schemas.customers.customer import CustomerProfileResponse
from app.schemas.equipment.equipment import (
    EquipmentCreate,
    EquipmentListResponse,
    EquipmentResponse,
    EquipmentUpdate,
)
from app.services.complaints import complaints as complaint_service
from app.services.customers.customers import get_customer_for_admin
from app.services.equipment import equipment as equipment_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


def _equipment_conflict_error() -> AppError:
    return AppError(
        "Equipment conflicts with an existing record.",
        status_code=status.HTTP_409_CONFLICT,
        code="equipment_conflict",
    )


def _equipment_in_use_error() -> AppError:
    return AppError(
        "Equipment has historical records and cannot be deleted.",
        status_code=status.HTTP_409_CONFLICT,
        code="equipment_in_use",
    )


@router.get(
    "/customers/{customer_id}",
    response_model=CustomerProfileResponse,
    summary="Admin: read a customer profile",
)
async def read_customer_profile(
    customer_id: uuid.UUID,
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileResponse:
    customer = await get_customer_for_admin(session, customer_id)
    return customer_profile_response(customer)


@router.get(
    "/customers/{customer_id}/equipment",
    response_model=EquipmentListResponse,
    summary="Admin: list a customer's equipment",
)
async def list_customer_equipment(
    customer_id: uuid.UUID,
    equipment_type: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> EquipmentListResponse:
    await get_customer_for_admin(session, customer_id)
    items, total = await equipment_service.list_equipment(
        session,
        customer_id=customer_id,
        equipment_type=equipment_type,
        limit=limit,
        offset=offset,
    )
    return EquipmentListResponse(
        items=[equipment_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/customers/{customer_id}/equipment",
    response_model=EquipmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: register equipment for a customer",
)
async def create_customer_equipment(
    customer_id: uuid.UUID,
    payload: EquipmentCreate,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> EquipmentResponse:
    customer = await get_customer_for_admin(session, customer_id)
    try:
        equipment = await equipment_service.create_equipment(
            session,
            customer=customer,
            data=payload,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _equipment_conflict_error() from exc

    await session.refresh(equipment)
    logger.info(
        "Equipment created by admin",
        extra={
            "event": "equipment_created",
            "actor_id": str(admin.id),
            "customer_id": str(customer.id),
            "equipment_id": str(equipment.id),
        },
    )
    return equipment_response(equipment)


@router.get(
    "/equipment",
    response_model=EquipmentListResponse,
    summary="Admin: list equipment",
)
async def list_all_equipment(
    customer_id: uuid.UUID | None = Query(default=None),
    equipment_type: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> EquipmentListResponse:
    items, total = await equipment_service.list_equipment(
        session,
        customer_id=customer_id,
        equipment_type=equipment_type,
        limit=limit,
        offset=offset,
    )
    return EquipmentListResponse(
        items=[equipment_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/equipment/{equipment_id}",
    response_model=EquipmentResponse,
    summary="Admin: read equipment",
)
async def read_equipment(
    equipment_id: uuid.UUID,
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> EquipmentResponse:
    equipment = await equipment_service.get_equipment(
        session,
        equipment_id,
    )
    return equipment_response(equipment)


@router.patch(
    "/equipment/{equipment_id}",
    response_model=EquipmentResponse,
    summary="Admin: update equipment",
)
async def update_equipment(
    equipment_id: uuid.UUID,
    payload: EquipmentUpdate,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> EquipmentResponse:
    equipment = await equipment_service.get_equipment(
        session,
        equipment_id,
    )
    try:
        updated = await equipment_service.update_equipment(
            session,
            equipment,
            payload,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _equipment_conflict_error() from exc

    await session.refresh(updated)
    logger.info(
        "Equipment updated by admin",
        extra={
            "event": "equipment_updated",
            "actor_id": str(admin.id),
            "customer_id": str(updated.customer_id),
            "equipment_id": str(updated.id),
        },
    )
    return equipment_response(updated)


@router.delete(
    "/equipment/{equipment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Admin: delete equipment when integrity permits it",
)
async def delete_equipment(
    equipment_id: uuid.UUID,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    equipment = await equipment_service.get_equipment(
        session,
        equipment_id,
    )
    customer_id = equipment.customer_id
    try:
        await equipment_service.delete_equipment(session, equipment)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _equipment_in_use_error() from exc

    logger.info(
        "Equipment deleted by admin",
        extra={
            "event": "equipment_deleted",
            "actor_id": str(admin.id),
            "customer_id": str(customer_id),
            "equipment_id": str(equipment_id),
        },
    )


@router.get(
    "/complaints",
    response_model=ComplaintListResponse,
    summary="Admin: list complaints",
)
async def list_all_complaints(
    customer_id: uuid.UUID | None = Query(default=None),
    complaint_status: ComplaintStatus | None = Query(
        default=None,
        alias="status",
    ),
    equipment_id: uuid.UUID | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> ComplaintListResponse:
    items, total = await complaint_service.list_complaints(
        session,
        customer_id=customer_id,
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


@router.get(
    "/complaints/{complaint_id}",
    response_model=ComplaintResponse,
    summary="Admin: read a complaint",
)
async def read_complaint(
    complaint_id: uuid.UUID,
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> ComplaintResponse:
    complaint = await complaint_service.get_complaint(
        session,
        complaint_id,
    )
    return complaint_response(complaint)


@router.get(
    "/complaints/{complaint_id}/history",
    response_model=ComplaintHistoryListResponse,
    summary="Admin: read a complaint's append-only history",
)
async def read_complaint_history(
    complaint_id: uuid.UUID,
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> ComplaintHistoryListResponse:
    await complaint_service.get_complaint(session, complaint_id)
    history = await complaint_service.list_complaint_history(
        session,
        complaint_id,
    )
    return ComplaintHistoryListResponse(
        items=[complaint_history_response(item) for item in history],
        total=len(history),
    )
