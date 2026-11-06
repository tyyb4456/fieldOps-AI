from __future__ import annotations

import uuid

from sqlalchemy import Select, false, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint
from app.models.customer import Customer
from app.models.enums import AssignmentStatus, UserRole
from app.models.equipment import Equipment
from app.models.technician import Technician
from app.models.technician_assignment import TechnicianAssignment
from app.models.user import User
from app.models.work_order import WorkOrder

TECHNICIAN_VISIBLE_ASSIGNMENT_STATUSES = (
    AssignmentStatus.OFFERED,
    AssignmentStatus.ACCEPTED,
)


class AccessDeniedError(Exception):
    """Raised when a user is not permitted to access an object.

    Callers should translate this to a 404 response for object lookups so
    that unauthorized users cannot probe for resource existence.
    """


def is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def is_customer(user: User) -> bool:
    return user.role == UserRole.CUSTOMER


def is_technician(user: User) -> bool:
    return user.role == UserRole.TECHNICIAN


def require_admin(user: User) -> None:
    if not is_admin(user):
        raise AccessDeniedError("Administrator role required")


def scope_equipment_for_customer(
    customer_id: uuid.UUID,
) -> Select[tuple[Equipment]]:
    return select(Equipment).where(Equipment.customer_id == customer_id)


def scope_complaints_for_customer(
    customer_id: uuid.UUID,
) -> Select[tuple[Complaint]]:
    return select(Complaint).where(Complaint.customer_id == customer_id)


def scope_equipment_for_user(user: User) -> Select[tuple[Equipment]]:
    if is_admin(user):
        return select(Equipment)

    if is_customer(user) and user.customer is not None:
        return scope_equipment_for_customer(user.customer.id)

    return select(Equipment).where(false())


def scope_complaints_for_user(user: User) -> Select[tuple[Complaint]]:
    if is_admin(user):
        return select(Complaint)

    if is_customer(user) and user.customer is not None:
        return scope_complaints_for_customer(user.customer.id)

    return select(Complaint).where(false())


def scope_work_orders_for_user(user: User) -> Select[tuple[WorkOrder]]:
    statement = select(WorkOrder)

    if is_admin(user):
        return statement

    if is_customer(user):
        return statement.where(
            WorkOrder.complaint_id.in_(
                select(Complaint.id)
                .join(Customer, Complaint.customer_id == Customer.id)
                .where(Customer.user_id == user.id)
            )
        )

    if is_technician(user):
        return statement.where(
            WorkOrder.id.in_(
                select(TechnicianAssignment.work_order_id)
                .join(
                    Technician,
                    TechnicianAssignment.technician_id == Technician.id,
                )
                .where(
                    Technician.user_id == user.id,
                    TechnicianAssignment.assignment_status.in_(
                        TECHNICIAN_VISIBLE_ASSIGNMENT_STATUSES
                    ),
                )
            )
        )

    return statement.where(false())


async def get_work_order_for_user(
    session: AsyncSession,
    user: User,
    work_order_id: uuid.UUID,
) -> WorkOrder:
    result = await session.execute(
        scope_work_orders_for_user(user).where(
            WorkOrder.id == work_order_id
        )
    )
    work_order = result.scalar_one_or_none()
    if work_order is None:
        raise AccessDeniedError("Work order not found")
    return work_order


async def get_customer_for_user(
    session: AsyncSession,
    user: User,
    customer_id: uuid.UUID,
) -> Customer:
    if is_admin(user):
        customer = await session.get(Customer, customer_id)
    elif is_customer(user):
        result = await session.execute(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.user_id == user.id,
            )
        )
        customer = result.scalar_one_or_none()
    else:
        raise AccessDeniedError("Customer not found")

    if customer is None:
        raise AccessDeniedError("Customer not found")
    return customer
