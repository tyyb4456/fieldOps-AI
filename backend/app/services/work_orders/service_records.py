from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AssignmentStatus, WorkOrderStatus
from app.models.service_record import ServiceRecord
from app.models.technician_assignment import TechnicianAssignment
from app.models.user import User
from app.models.work_order import WorkOrder
from app.schemas.work_orders.service_record import (
    ServiceRecordCreate,
    ServiceRecordUpdate,
)
from app.services.shared.authorization import (
    AccessDeniedError,
    get_service_record_for_user,
    get_work_order_for_user,
    is_technician,
    scope_service_records_for_user,
)

SERVICE_RECORD_WORK_ORDER_STATUSES = frozenset(
    {
        WorkOrderStatus.ACCEPTED,
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.AWAITING_PARTS,
    }
)

EDITABLE_SERVICE_RECORD_WORK_ORDER_STATUSES = frozenset(
    {
        WorkOrderStatus.ACCEPTED,
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.AWAITING_PARTS,
    }
)


class ServiceRecordStateError(Exception):
    """Raised when a service record is not allowed in the current state."""


class AssignmentRequiredError(Exception):
    """Raised when a technician lacks an accepted assignment."""


async def _lock_work_order(
    session: AsyncSession,
    work_order_id: uuid.UUID,
) -> WorkOrder:
    result = await session.execute(
        select(WorkOrder)
        .where(WorkOrder.id == work_order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    work_order = result.scalar_one_or_none()
    if work_order is None:
        raise AccessDeniedError("Work order not found")
    return work_order


async def list_service_records(
    session: AsyncSession,
    user: User,
    *,
    work_order_id: uuid.UUID | None,
    equipment_id: uuid.UUID | None,
    technician_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[ServiceRecord], int]:
    filters = []
    if work_order_id is not None:
        filters.append(ServiceRecord.work_order_id == work_order_id)
    if equipment_id is not None:
        filters.append(ServiceRecord.equipment_id == equipment_id)
    if technician_id is not None:
        filters.append(ServiceRecord.technician_id == technician_id)

    scoped = scope_service_records_for_user(user).where(*filters)
    total = await session.scalar(
        select(func.count()).select_from(scoped.subquery())
    )
    statement = (
        scoped.order_by(
            ServiceRecord.recorded_at.desc(),
            ServiceRecord.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(statement)
    return list(result.scalars().all()), int(total or 0)


async def get_service_record(
    session: AsyncSession,
    user: User,
    service_record_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> ServiceRecord:
    return await get_service_record_for_user(
        session,
        user,
        service_record_id,
        for_update=for_update,
    )


async def create_service_record(
    session: AsyncSession,
    *,
    user: User,
    work_order_id: uuid.UUID,
    data: ServiceRecordCreate,
) -> ServiceRecord:
    work_order = await get_work_order_for_user(
        session,
        user,
        work_order_id,
        for_update=True,
    )

    if work_order.status not in SERVICE_RECORD_WORK_ORDER_STATUSES:
        raise ServiceRecordStateError(
            "Work order is not in a state that permits service activity"
        )

    technician = user.technician
    if technician is None:
        raise AccessDeniedError("Work order not found")

    assignment = await session.scalar(
        select(TechnicianAssignment.id)
        .where(
            TechnicianAssignment.work_order_id == work_order.id,
            TechnicianAssignment.technician_id == technician.id,
            TechnicianAssignment.assignment_status
            == AssignmentStatus.ACCEPTED,
        )
        .with_for_update()
    )
    if assignment is None:
        raise AssignmentRequiredError(
            "An accepted assignment is required to record service activity"
        )

    service_record = ServiceRecord(
        equipment_id=work_order.equipment_id,
        work_order_id=work_order.id,
        technician_id=technician.id,
        findings=data.findings,
        work_performed=data.work_performed,
        parts_used=data.parts_used,
    )
    session.add(service_record)
    await session.flush()
    return service_record


async def update_service_record(
    session: AsyncSession,
    *,
    user: User,
    service_record_id: uuid.UUID,
    data: ServiceRecordUpdate,
) -> ServiceRecord:
    if not is_technician(user):
        raise AccessDeniedError("Service record not found")

    service_record = await get_service_record_for_user(
        session,
        user,
        service_record_id,
    )
    work_order = await _lock_work_order(
        session,
        service_record.work_order_id,
    )
    service_record = await get_service_record_for_user(
        session,
        user,
        service_record_id,
        for_update=True,
    )

    technician = user.technician
    if (
        technician is None
        or service_record.technician_id != technician.id
    ):
        raise AccessDeniedError("Service record not found")

    if (
        work_order.status
        not in EDITABLE_SERVICE_RECORD_WORK_ORDER_STATUSES
    ):
        raise ServiceRecordStateError(
            "Submitted service records are immutable once the work order "
            "leaves active service"
        )

    for field in data.model_fields_set:
        setattr(service_record, field, getattr(data, field))

    if not service_record.findings and not service_record.work_performed:
        raise ServiceRecordStateError(
            "A service record must retain findings or work performed"
        )

    await session.flush()
    return service_record
