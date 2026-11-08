from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.complaint import Complaint
from app.models.enums import (
    AssignmentStatus,
    ComplaintStatus,
    Priority,
    UserRole,
    WorkOrderStatus,
)
from app.models.equipment import Equipment
from app.models.service_record import ServiceRecord
from app.models.technician import Technician
from app.models.technician_assignment import TechnicianAssignment
from app.models.user import User
from app.models.work_order import WorkOrder
from app.schemas.work_order import (
    WorkOrderCreate,
    WorkOrderUpdate,
)
from app.services import complaints as complaint_service
from app.services.authorization import (
    AccessDeniedError,
    get_work_order_for_user,
    is_admin,
    is_technician,
    scope_work_orders_for_user,
)

ACTIVE_ASSIGNMENT_STATUSES = (
    AssignmentStatus.OFFERED,
    AssignmentStatus.ACCEPTED,
)

COMPLAINT_STATUSES_ELIGIBLE_FOR_CONVERSION = frozenset(
    {ComplaintStatus.READY_FOR_WORK_ORDER}
)

EDITABLE_WORK_ORDER_STATUSES = frozenset(
    {
        WorkOrderStatus.DRAFT,
        WorkOrderStatus.VALIDATED,
        WorkOrderStatus.AWAITING_ASSIGNMENT,
    }
)

# Administrator-controlled lifecycle. Technician-specific transitions are
# intentionally separate because starting or submitting work requires an
# accepted assignment, while administrative transitions do not.
ADMIN_TRANSITIONS: dict[
    WorkOrderStatus, frozenset[WorkOrderStatus]
] = {
    WorkOrderStatus.DRAFT: frozenset(
        {WorkOrderStatus.VALIDATED, WorkOrderStatus.CANCELLED}
    ),
    WorkOrderStatus.VALIDATED: frozenset(
        {
            WorkOrderStatus.AWAITING_ASSIGNMENT,
            WorkOrderStatus.CANCELLED,
        }
    ),
    WorkOrderStatus.AWAITING_ASSIGNMENT: frozenset(
        {WorkOrderStatus.ESCALATED, WorkOrderStatus.CANCELLED}
    ),
    WorkOrderStatus.ASSIGNED: frozenset(
        {WorkOrderStatus.ESCALATED, WorkOrderStatus.CANCELLED}
    ),
    WorkOrderStatus.ACCEPTED: frozenset(
        {WorkOrderStatus.ESCALATED, WorkOrderStatus.CANCELLED}
    ),
    WorkOrderStatus.IN_PROGRESS: frozenset(
        {
            WorkOrderStatus.PENDING_VERIFICATION,
            WorkOrderStatus.ESCALATED,
            WorkOrderStatus.CANCELLED,
        }
    ),
    WorkOrderStatus.AWAITING_PARTS: frozenset(
        {
            WorkOrderStatus.IN_PROGRESS,
            WorkOrderStatus.ESCALATED,
            WorkOrderStatus.CANCELLED,
        }
    ),
    WorkOrderStatus.PENDING_VERIFICATION: frozenset(
        {
            WorkOrderStatus.COMPLETED,
            WorkOrderStatus.IN_PROGRESS,
            WorkOrderStatus.ESCALATED,
        }
    ),
    WorkOrderStatus.ESCALATED: frozenset(
        {WorkOrderStatus.AWAITING_ASSIGNMENT, WorkOrderStatus.CANCELLED}
    ),
    WorkOrderStatus.COMPLETED: frozenset(),
    WorkOrderStatus.CANCELLED: frozenset(),
}

TECHNICIAN_TRANSITIONS: dict[
    WorkOrderStatus, frozenset[WorkOrderStatus]
] = {
    WorkOrderStatus.ACCEPTED: frozenset({WorkOrderStatus.IN_PROGRESS}),
    WorkOrderStatus.IN_PROGRESS: frozenset(
        {
            WorkOrderStatus.AWAITING_PARTS,
            WorkOrderStatus.PENDING_VERIFICATION,
            WorkOrderStatus.ESCALATED,
        }
    ),
    WorkOrderStatus.AWAITING_PARTS: frozenset(
        {WorkOrderStatus.IN_PROGRESS}
    ),
}


class WorkOrderAlreadyExistsError(Exception):
    """Raised when an eligible complaint already has a work order."""


class InvalidComplaintConversionError(Exception):
    """Raised when a complaint cannot be converted to a work order."""


class InvalidWorkOrderTransitionError(Exception):
    """Raised when a requested work-order state change is not permitted."""


class WorkOrderNotEditableError(Exception):
    """Raised when work-order fields are edited after operational work."""


def _allowed_transitions(user: User) -> dict[
    WorkOrderStatus, frozenset[WorkOrderStatus]
]:
    if is_admin(user):
        return ADMIN_TRANSITIONS
    if is_technician(user):
        return TECHNICIAN_TRANSITIONS
    return {}


async def list_work_orders(
    session: AsyncSession,
    user: User,
    *,
    status: WorkOrderStatus | None,
    priority: Priority | None,
    complaint_id: uuid.UUID | None,
    equipment_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[WorkOrder], int]:
    filters = []
    if status is not None:
        filters.append(WorkOrder.status == status)
    if priority is not None:
        filters.append(WorkOrder.priority == priority)
    if complaint_id is not None:
        filters.append(WorkOrder.complaint_id == complaint_id)
    if equipment_id is not None:
        filters.append(WorkOrder.equipment_id == equipment_id)

    scoped = scope_work_orders_for_user(user).where(*filters)
    total = await session.scalar(
        select(func.count()).select_from(scoped.subquery())
    )

    statement = (
        scoped.order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(statement)
    return list(result.scalars().all()), int(total or 0)


async def get_work_order(
    session: AsyncSession,
    user: User,
    work_order_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> WorkOrder:
    return await get_work_order_for_user(
        session,
        user,
        work_order_id,
        for_update=for_update,
    )


async def create_work_order_from_complaint(
    session: AsyncSession,
    *,
    complaint_id: uuid.UUID,
    data: WorkOrderCreate,
    actor_id: uuid.UUID,
) -> WorkOrder:
    """Convert one eligible complaint into one work order atomically.

    The complaint row lock serializes concurrent conversions, so only one
    transaction can observe the eligible status. The unique constraint on
    ``work_orders.complaint_id`` is the database backstop.
    """
    complaint = await complaint_service.get_complaint(
        session,
        complaint_id,
        for_update=True,
    )

    existing = await session.scalar(
        select(WorkOrder).where(
            WorkOrder.complaint_id == complaint.id
        )
    )
    if existing is not None:
        raise WorkOrderAlreadyExistsError(
            "A work order already exists for this complaint"
        )

    if complaint.status not in COMPLAINT_STATUSES_ELIGIBLE_FOR_CONVERSION:
        raise InvalidComplaintConversionError(
            "Complaint is not eligible for work-order conversion"
        )

    if complaint.equipment_id is None:
        raise InvalidComplaintConversionError(
            "Complaint has no identified equipment"
        )

    equipment = await session.get(Equipment, complaint.equipment_id)
    if equipment is None or equipment.customer_id != complaint.customer_id:
        raise InvalidComplaintConversionError(
            "Complaint equipment does not belong to the complaint customer"
        )

    work_order = WorkOrder(
        complaint_id=complaint.id,
        equipment_id=complaint.equipment_id,
        title=data.title,
        description=data.description,
        diagnostic_checklist=data.diagnostic_checklist,
        priority=data.priority or complaint.priority,
        status=WorkOrderStatus.DRAFT,
    )
    session.add(work_order)
    await session.flush()

    previous_status = complaint.status
    complaint.status = ComplaintStatus.CONVERTED
    await complaint_service.append_complaint_history(
        session,
        complaint_id=complaint.id,
        event_type="converted",
        from_status=previous_status,
        to_status=ComplaintStatus.CONVERTED,
        changed_fields={
            "status": {
                "from": previous_status.value,
                "to": ComplaintStatus.CONVERTED.value,
            }
        },
        actor_id=actor_id,
    )
    await session.flush()
    return work_order


async def update_work_order(
    session: AsyncSession,
    work_order: WorkOrder,
    data: WorkOrderUpdate,
) -> WorkOrder:
    if work_order.status not in EDITABLE_WORK_ORDER_STATUSES:
        raise WorkOrderNotEditableError(
            "Work-order fields are not editable in the current state"
        )

    for field in data.model_fields_set:
        setattr(work_order, field, getattr(data, field))

    await session.flush()
    return work_order


async def _require_accepted_assignment(
    session: AsyncSession,
    work_order: WorkOrder,
    technician_id: uuid.UUID,
) -> None:
    assignment = await session.scalar(
        select(TechnicianAssignment.id).where(
            TechnicianAssignment.work_order_id == work_order.id,
            TechnicianAssignment.technician_id == technician_id,
            TechnicianAssignment.assignment_status
            == AssignmentStatus.ACCEPTED,
        )
    )
    if assignment is None:
        raise InvalidWorkOrderTransitionError(
            "An accepted technician assignment is required"
        )


async def _count_service_records(
    session: AsyncSession,
    work_order_id: uuid.UUID,
    *,
    require_work_performed: bool,
) -> int:
    statement = select(func.count(ServiceRecord.id)).where(
        ServiceRecord.work_order_id == work_order_id
    )
    if require_work_performed:
        statement = statement.where(
            ServiceRecord.work_performed.is_not(None),
            func.length(func.btrim(ServiceRecord.work_performed)) > 0,
        )
    return int(await session.scalar(statement) or 0)


async def _withdraw_active_assignments(
    session: AsyncSession,
    work_order_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(TechnicianAssignment)
        .where(
            TechnicianAssignment.work_order_id == work_order_id,
            TechnicianAssignment.assignment_status.in_(
                ACTIVE_ASSIGNMENT_STATUSES
            ),
        )
        .order_by(TechnicianAssignment.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    for assignment in result.scalars().all():
        assignment.assignment_status = AssignmentStatus.WITHDRAWN
    await session.flush()


async def transition_work_order(
    session: AsyncSession,
    *,
    user: User,
    work_order_id: uuid.UUID,
    target_status: WorkOrderStatus,
) -> WorkOrder:
    work_order = await get_work_order_for_user(
        session,
        user,
        work_order_id,
        for_update=True,
    )
    previous_status = work_order.status

    if target_status == previous_status:
        raise InvalidWorkOrderTransitionError(
            "Work order is already in the requested state"
        )

    allowed = _allowed_transitions(user).get(
        previous_status,
        frozenset(),
    )
    if target_status not in allowed:
        raise InvalidWorkOrderTransitionError(
            f"Cannot move work order from {previous_status.value} "
            f"to {target_status.value}"
        )

    if is_technician(user):
        technician = user.technician
        if technician is None:
            raise AccessDeniedError("Work order not found")
        await _require_accepted_assignment(
            session,
            work_order,
            technician.id,
        )

    if target_status is WorkOrderStatus.PENDING_VERIFICATION:
        if await _count_service_records(
            session,
            work_order.id,
            require_work_performed=False,
        ) == 0:
            raise InvalidWorkOrderTransitionError(
                "A service record is required before verification"
            )

    if target_status is WorkOrderStatus.COMPLETED:
        if await _count_service_records(
            session,
            work_order.id,
            require_work_performed=True,
        ) == 0:
            raise InvalidWorkOrderTransitionError(
                "Completion evidence with work performed is required"
            )

    if target_status in (
        WorkOrderStatus.AWAITING_ASSIGNMENT,
        WorkOrderStatus.CANCELLED,
    ):
        await _withdraw_active_assignments(session, work_order.id)

    work_order.status = target_status
    await session.flush()
    return work_order


async def list_eligible_technicians(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> tuple[list[Technician], int]:
    """Return active technician profiles for administrator assignment."""
    conditions = (
        User.role == UserRole.TECHNICIAN,
        User.is_active.is_(True),
        Technician.is_available.is_(True),
    )
    total = await session.scalar(
        select(func.count())
        .select_from(Technician)
        .join(User, Technician.user_id == User.id)
        .where(*conditions)
    )
    result = await session.execute(
        select(Technician)
        .join(User, Technician.user_id == User.id)
        .options(selectinload(Technician.user))
        .where(*conditions)
        .order_by(User.full_name.asc(), Technician.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)
