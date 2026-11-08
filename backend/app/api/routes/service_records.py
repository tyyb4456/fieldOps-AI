from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    get_current_user,
    require_technician_user,
)
from app.api.serializers import service_record_response
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.service_record import (
    ServiceRecordCreate,
    ServiceRecordListResponse,
    ServiceRecordResponse,
    ServiceRecordUpdate,
)
from app.services import service_records as service_record_service
from app.services import work_orders as work_order_service
from app.services.service_records import (
    AssignmentRequiredError,
    ServiceRecordStateError,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Service Records"])


def _service_record_conflict_error() -> AppError:
    return AppError(
        "Service record conflicts with the work order or equipment.",
        status_code=status.HTTP_409_CONFLICT,
        code="service_record_conflict",
    )


def _invalid_service_record_state_error() -> AppError:
    return AppError(
        "Service record cannot be changed in the current state.",
        status_code=status.HTTP_409_CONFLICT,
        code="invalid_service_record_state",
    )


def _assignment_required_error() -> AppError:
    return AppError(
        "An accepted assignment is required to record service activity.",
        status_code=status.HTTP_409_CONFLICT,
        code="assignment_required",
    )


@router.get(
    "/service-records",
    response_model=ServiceRecordListResponse,
    summary="List service records visible to the authenticated user",
)
@router.get(
    "/admin/service-records",
    response_model=ServiceRecordListResponse,
    summary="Admin: list all service records",
)
async def list_service_records(
    work_order_id: uuid.UUID | None = Query(default=None),
    equipment_id: uuid.UUID | None = Query(default=None),
    technician_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ServiceRecordListResponse:
    items, total = await service_record_service.list_service_records(
        session,
        current_user,
        work_order_id=work_order_id,
        equipment_id=equipment_id,
        technician_id=technician_id,
        limit=limit,
        offset=offset,
    )
    return ServiceRecordListResponse(
        items=[service_record_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/service-records/{service_record_id}",
    response_model=ServiceRecordResponse,
    summary="Read a service record visible to the authenticated user",
)
@router.get(
    "/admin/service-records/{service_record_id}",
    response_model=ServiceRecordResponse,
    summary="Admin: read a service record",
    include_in_schema=False,
)
async def read_service_record(
    service_record_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ServiceRecordResponse:
    service_record = await service_record_service.get_service_record(
        session,
        current_user,
        service_record_id,
    )
    return service_record_response(service_record)


@router.get(
    "/work-orders/{work_order_id}/service-records",
    response_model=ServiceRecordListResponse,
    summary="List the service records for an accessible work order",
)
async def list_work_order_service_records(
    work_order_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ServiceRecordListResponse:
    await work_order_service.get_work_order(
        session,
        current_user,
        work_order_id,
    )
    items, total = await service_record_service.list_service_records(
        session,
        current_user,
        work_order_id=work_order_id,
        equipment_id=None,
        technician_id=None,
        limit=limit,
        offset=offset,
    )
    return ServiceRecordListResponse(
        items=[service_record_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/work-orders/{work_order_id}/service-records",
    response_model=ServiceRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Technician: record service activity on an accepted job",
)
async def create_service_record(
    work_order_id: uuid.UUID,
    payload: ServiceRecordCreate,
    technician_user: User = Depends(require_technician_user),
    session: AsyncSession = Depends(get_db_session),
) -> ServiceRecordResponse:
    try:
        service_record = (
            await service_record_service.create_service_record(
                session,
                user=technician_user,
                work_order_id=work_order_id,
                data=payload,
            )
        )
        await session.commit()
    except ServiceRecordStateError as exc:
        await session.rollback()
        raise _invalid_service_record_state_error() from exc
    except AssignmentRequiredError as exc:
        await session.rollback()
        raise _assignment_required_error() from exc
    except IntegrityError as exc:
        await session.rollback()
        raise _service_record_conflict_error() from exc

    await session.refresh(service_record)
    logger.info(
        "Service record created",
        extra={
            "event": "service_record_created",
            "actor_id": str(technician_user.id),
            "work_order_id": str(service_record.work_order_id),
            "equipment_id": str(service_record.equipment_id),
            "service_record_id": str(service_record.id),
        },
    )
    return service_record_response(service_record)


@router.patch(
    "/service-records/{service_record_id}",
    response_model=ServiceRecordResponse,
    summary="Technician: update their own active service record",
)
async def update_service_record(
    service_record_id: uuid.UUID,
    payload: ServiceRecordUpdate,
    technician_user: User = Depends(require_technician_user),
    session: AsyncSession = Depends(get_db_session),
) -> ServiceRecordResponse:
    try:
        service_record = (
            await service_record_service.update_service_record(
                session,
                user=technician_user,
                service_record_id=service_record_id,
                data=payload,
            )
        )
        await session.commit()
    except ServiceRecordStateError as exc:
        await session.rollback()
        raise _invalid_service_record_state_error() from exc

    await session.refresh(service_record)
    logger.info(
        "Service record updated",
        extra={
            "event": "service_record_updated",
            "actor_id": str(technician_user.id),
            "work_order_id": str(service_record.work_order_id),
            "service_record_id": str(service_record.id),
        },
    )
    return service_record_response(service_record)
