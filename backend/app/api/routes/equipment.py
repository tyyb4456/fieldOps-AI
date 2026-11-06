from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    get_current_customer,
    require_customer_user,
)
from app.api.serializers import equipment_response
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.customer import Customer
from app.models.equipment import Equipment
from app.models.user import User
from app.schemas.equipment import (
    EquipmentCreate,
    EquipmentListResponse,
    EquipmentResponse,
    EquipmentUpdate,
)
from app.services import equipment as equipment_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/customers/me/equipment",
    tags=["Equipment"],
)


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
    "",
    response_model=EquipmentListResponse,
    summary="List the authenticated customer's equipment",
)
async def list_own_equipment(
    equipment_type: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> EquipmentListResponse:
    items, total = await equipment_service.list_equipment(
        session,
        customer_id=customer.id,
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
    "",
    response_model=EquipmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register equipment for the authenticated customer",
)
async def create_own_equipment(
    payload: EquipmentCreate,
    current_user: User = Depends(require_customer_user),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> EquipmentResponse:
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
        "Equipment created",
        extra={
            "event": "equipment_created",
            "actor_id": str(current_user.id),
            "customer_id": str(customer.id),
            "equipment_id": str(equipment.id),
        },
    )
    return equipment_response(equipment)


@router.get(
    "/{equipment_id}",
    response_model=EquipmentResponse,
    summary="Retrieve one of the authenticated customer's equipment",
)
async def read_own_equipment(
    equipment_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> EquipmentResponse:
    equipment = await equipment_service.get_equipment_for_customer(
        session,
        customer.id,
        equipment_id,
    )
    return equipment_response(equipment)


@router.patch(
    "/{equipment_id}",
    response_model=EquipmentResponse,
    summary="Update one of the authenticated customer's equipment",
)
async def update_own_equipment(
    equipment_id: uuid.UUID,
    payload: EquipmentUpdate,
    current_user: User = Depends(require_customer_user),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> EquipmentResponse:
    equipment = await equipment_service.get_equipment_for_customer(
        session,
        customer.id,
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
        "Equipment updated",
        extra={
            "event": "equipment_updated",
            "actor_id": str(current_user.id),
            "customer_id": str(customer.id),
            "equipment_id": str(updated.id),
        },
    )
    return equipment_response(updated)


@router.delete(
    "/{equipment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one of the authenticated customer's equipment",
)
async def delete_own_equipment(
    equipment_id: uuid.UUID,
    current_user: User = Depends(require_customer_user),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    equipment = await equipment_service.get_equipment_for_customer(
        session,
        customer.id,
        equipment_id,
    )
    try:
        await equipment_service.delete_equipment(session, equipment)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _equipment_in_use_error() from exc

    logger.info(
        "Equipment deleted",
        extra={
            "event": "equipment_deleted",
            "actor_id": str(current_user.id),
            "customer_id": str(customer.id),
            "equipment_id": str(equipment_id),
        },
    )
