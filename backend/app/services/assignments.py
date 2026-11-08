from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import (
    AssignmentStatus,
    UserRole,
    WorkOrderStatus,
)
from app.models.technician import Technician
from app.models.technician_assignment import TechnicianAssignment
from app.models.user import User
from app.models.work_order import WorkOrder
from app.services.authorization import (
    AccessDeniedError,
    get_assignment_for_user,
    scope_assignments_for_user,
)

ACTIVE_ASSIGNMENT_INDEX_NAME = (
    "uq_technician_assignments_active_work_order"
)

ACTIVE_ASSIGNMENT_STATUSES = (
    AssignmentStatus.OFFERED,
    AssignmentStatus.ACCEPTED,
)

INITIAL_ASSIGNABLE_WORK_ORDER_STATUSES = frozenset(
    {
        WorkOrderStatus.VALIDATED,
        WorkOrderStatus.AWAITING_ASSIGNMENT,
    }
)

REASSIGNABLE_WORK_ORDER_STATUSES = frozenset(
    {
        WorkOrderStatus.VALIDATED,
        WorkOrderStatus.AWAITING_ASSIGNMENT,
        WorkOrderStatus.ASSIGNED,
        WorkOrderStatus.ACCEPTED,
    }
)

WITHDRAWABLE_WORK_ORDER_STATUSES = frozenset(
    {
        WorkOrderStatus.AWAITING_ASSIGNMENT,
        WorkOrderStatus.ASSIGNED,
        WorkOrderStatus.ACCEPTED,
    }
)


class AssignmentConflictError(Exception):
    """Raised when a work order already has an active assignment."""


class InvalidAssignmentStateError(Exception):
    """Raised when an assignment lifecycle transition is not permitted."""


class TechnicianNotEligibleError(Exception):
    """Raised when the selected technician cannot receive work."""


def is_active_assignment_conflict(exc: IntegrityError) -> bool:
    """Return True only for the active-assignment unique-index conflict."""
    original = exc.orig
    constraint_name = getattr(original, "constraint_name", None)
    if constraint_name == ACTIVE_ASSIGNMENT_INDEX_NAME:
        return True

    diagnostics = getattr(original, "diag", None)
    if (
        getattr(diagnostics, "constraint_name", None)
        == ACTIVE_ASSIGNMENT_INDEX_NAME
    ):
        return True

    return ACTIVE_ASSIGNMENT_INDEX_NAME in str(original)


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


async def _get_eligible_technician(
    session: AsyncSession,
    technician_id: uuid.UUID,
) -> Technician:
    result = await session.execute(
        select(Technician)
        .options(selectinload(Technician.user))
        .where(Technician.id == technician_id)
    )
    technician = result.scalar_one_or_none()
    if technician is None:
        raise TechnicianNotEligibleError("Technician not found")

    user = technician.user
    if user.role is not UserRole.TECHNICIAN:
        raise TechnicianNotEligibleError(
            "Selected user does not have the technician role"
        )
    if not user.is_active:
        raise TechnicianNotEligibleError("Technician account is inactive")
    if not technician.is_available:
        raise TechnicianNotEligibleError("Technician is not available")
    return technician


async def list_assignments(
    session: AsyncSession,
    user: User,
    *,
    status: AssignmentStatus | None,
    work_order_id: uuid.UUID | None,
    technician_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[TechnicianAssignment], int]:
    filters = []
    if status is not None:
        filters.append(
            TechnicianAssignment.assignment_status == status
        )
    if work_order_id is not None:
        filters.append(
            TechnicianAssignment.work_order_id == work_order_id
        )
    if technician_id is not None:
        filters.append(
            TechnicianAssignment.technician_id == technician_id
        )

    scoped = scope_assignments_for_user(user).where(*filters)
    total = await session.scalar(
        select(func.count()).select_from(scoped.subquery())
    )
    statement = (
        scoped.order_by(
            TechnicianAssignment.assigned_at.desc(),
            TechnicianAssignment.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(statement)
    return list(result.scalars().all()), int(total or 0)


async def get_assignment(
    session: AsyncSession,
    user: User,
    assignment_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> TechnicianAssignment:
    return await get_assignment_for_user(
        session,
        user,
        assignment_id,
        for_update=for_update,
    )


async def create_assignment(
    session: AsyncSession,
    *,
    work_order_id: uuid.UUID,
    technician_id: uuid.UUID,
    reassign: bool = False,
) -> TechnicianAssignment:
    """Offer a work order to an eligible technician.

    The work-order row lock serializes concurrent assignment attempts and
    reassignment/acceptance races. The partial unique index on active
    assignments is the database-level backstop.
    """
    work_order = await _lock_work_order(session, work_order_id)

    result = await session.execute(
        select(TechnicianAssignment)
        .where(
            TechnicianAssignment.work_order_id == work_order.id,
            TechnicianAssignment.assignment_status.in_(
                ACTIVE_ASSIGNMENT_STATUSES
            ),
        )
        .order_by(TechnicianAssignment.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    active_assignments = list(result.scalars().all())
    if active_assignments and not reassign:
        raise AssignmentConflictError(
            "Work order already has an active assignment"
        )

    allowed_statuses = (
        REASSIGNABLE_WORK_ORDER_STATUSES
        if reassign
        else INITIAL_ASSIGNABLE_WORK_ORDER_STATUSES
    )
    if work_order.status not in allowed_statuses:
        raise InvalidAssignmentStateError(
            "Work order is not accepting technician assignments"
        )

    technician = await _get_eligible_technician(session, technician_id)

    for existing in active_assignments:
        existing.assignment_status = AssignmentStatus.WITHDRAWN

    assignment = TechnicianAssignment(
        work_order_id=work_order.id,
        technician_id=technician.id,
        assignment_status=AssignmentStatus.OFFERED,
    )
    session.add(assignment)
    await session.flush()

    work_order.status = WorkOrderStatus.ASSIGNED
    await session.flush()
    return assignment


async def _find_technician_offer(
    session: AsyncSession,
    *,
    user: User,
    work_order_id: uuid.UUID,
) -> uuid.UUID:
    technician = user.technician
    if technician is None:
        raise AccessDeniedError("Work order not found")

    assignment_id = await session.scalar(
        select(TechnicianAssignment.id)
        .where(
            TechnicianAssignment.work_order_id == work_order_id,
            TechnicianAssignment.technician_id == technician.id,
            TechnicianAssignment.assignment_status
            == AssignmentStatus.OFFERED,
        )
        .order_by(TechnicianAssignment.assigned_at.desc())
    )
    if assignment_id is None:
        raise AccessDeniedError("Work order not found")
    return assignment_id


async def accept_assignment(
    session: AsyncSession,
    *,
    user: User,
    assignment_id: uuid.UUID,
) -> TechnicianAssignment:
    assignment = await get_assignment_for_user(
        session,
        user,
        assignment_id,
    )
    work_order = await _lock_work_order(
        session,
        assignment.work_order_id,
    )
    assignment = await get_assignment_for_user(
        session,
        user,
        assignment_id,
        for_update=True,
    )

    if assignment.assignment_status is not AssignmentStatus.OFFERED:
        raise InvalidAssignmentStateError(
            "Only an offered assignment can be accepted"
        )
    if work_order.status is not WorkOrderStatus.ASSIGNED:
        raise InvalidAssignmentStateError(
            "Work order is not awaiting technician acceptance"
        )

    assignment.assignment_status = AssignmentStatus.ACCEPTED
    assignment.accepted_at = datetime.now(timezone.utc)
    work_order.status = WorkOrderStatus.ACCEPTED
    await session.flush()
    return assignment


async def accept_work_order_offer(
    session: AsyncSession,
    *,
    user: User,
    work_order_id: uuid.UUID,
) -> TechnicianAssignment:
    assignment_id = await _find_technician_offer(
        session,
        user=user,
        work_order_id=work_order_id,
    )
    return await accept_assignment(
        session,
        user=user,
        assignment_id=assignment_id,
    )


async def reject_assignment(
    session: AsyncSession,
    *,
    user: User,
    assignment_id: uuid.UUID,
) -> TechnicianAssignment:
    assignment = await get_assignment_for_user(
        session,
        user,
        assignment_id,
    )
    work_order = await _lock_work_order(
        session,
        assignment.work_order_id,
    )
    assignment = await get_assignment_for_user(
        session,
        user,
        assignment_id,
        for_update=True,
    )

    if assignment.assignment_status is not AssignmentStatus.OFFERED:
        raise InvalidAssignmentStateError(
            "Only an offered assignment can be rejected"
        )
    if work_order.status is not WorkOrderStatus.ASSIGNED:
        raise InvalidAssignmentStateError(
            "Work order is not awaiting technician acceptance"
        )

    assignment.assignment_status = AssignmentStatus.REJECTED
    assignment.rejected_at = datetime.now(timezone.utc)
    work_order.status = WorkOrderStatus.AWAITING_ASSIGNMENT
    await session.flush()
    return assignment


async def reject_work_order_offer(
    session: AsyncSession,
    *,
    user: User,
    work_order_id: uuid.UUID,
) -> TechnicianAssignment:
    assignment_id = await _find_technician_offer(
        session,
        user=user,
        work_order_id=work_order_id,
    )
    return await reject_assignment(
        session,
        user=user,
        assignment_id=assignment_id,
    )


async def withdraw_assignment(
    session: AsyncSession,
    *,
    user: User,
    assignment_id: uuid.UUID,
) -> TechnicianAssignment:
    assignment = await get_assignment_for_user(
        session,
        user,
        assignment_id,
    )
    work_order = await _lock_work_order(
        session,
        assignment.work_order_id,
    )
    assignment = await get_assignment_for_user(
        session,
        user,
        assignment_id,
        for_update=True,
    )

    if assignment.assignment_status not in ACTIVE_ASSIGNMENT_STATUSES:
        raise InvalidAssignmentStateError(
            "Only an active assignment can be withdrawn"
        )
    if work_order.status not in WITHDRAWABLE_WORK_ORDER_STATUSES:
        raise InvalidAssignmentStateError(
            "Work order has progressed too far to withdraw the assignment"
        )

    assignment.assignment_status = AssignmentStatus.WITHDRAWN
    work_order.status = WorkOrderStatus.AWAITING_ASSIGNMENT
    await session.flush()
    return assignment
