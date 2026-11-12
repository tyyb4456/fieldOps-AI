from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint
from app.models.customer import Customer
from app.models.enums import (
    AssignmentStatus,
    ComplaintChannel,
    UserRole,
)
from app.models.equipment import Equipment
from app.models.technician import Technician
from app.models.technician_assignment import TechnicianAssignment
from app.models.user import User
from app.models.work_order import WorkOrder
from app.services.authorization import (
    AccessDeniedError,
    get_customer_for_user,
    get_work_order_for_user,
    scope_work_orders_for_user,
)


async def add_user(
    session: AsyncSession,
    *,
    role: UserRole = UserRole.CUSTOMER,
) -> User:
    user = User(
        full_name=f"{role.value.title()} User",
        email=f"{uuid.uuid4().hex}@example.com",
        password_hash=None,
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


async def add_customer(
    session: AsyncSession,
) -> tuple[User, Customer]:
    user = await add_user(session, role=UserRole.CUSTOMER)
    customer = Customer(user=user)
    session.add(customer)
    await session.flush()
    return user, customer


async def add_technician(
    session: AsyncSession,
) -> tuple[User, Technician]:
    user = await add_user(session, role=UserRole.TECHNICIAN)
    technician = Technician(user=user)
    session.add(technician)
    await session.flush()
    return user, technician


async def add_work_order(
    session: AsyncSession,
    customer: Customer,
) -> tuple[Equipment, Complaint, WorkOrder]:
    equipment = Equipment(
        customer=customer,
        manufacturer="Acme Solar",
        model="INV-5000",
        serial_number=uuid.uuid4().hex[:12],
        equipment_type="solar_inverter",
    )
    complaint = Complaint(
        customer=customer,
        equipment=equipment,
        description="The inverter stopped generating power.",
        channel=ComplaintChannel.WEB,
    )
    work_order = WorkOrder(
        complaint=complaint,
        equipment=equipment,
        title="Inspect inverter",
        description="Inspect the inverter and restore generation.",
    )
    session.add_all([equipment, complaint, work_order])
    await session.flush()
    return equipment, complaint, work_order


async def test_customer_can_access_own_profile(
    db_session: AsyncSession,
) -> None:
    user, customer = await add_customer(db_session)

    result = await get_customer_for_user(db_session, user, customer.id)

    assert result.id == customer.id


async def test_customer_cannot_access_other_profile(
    db_session: AsyncSession,
) -> None:
    _, own_customer = await add_customer(db_session)
    user, _ = await add_customer(db_session)

    with pytest.raises(AccessDeniedError):
        await get_customer_for_user(
            db_session,
            user,
            own_customer.id,
        )


async def test_admin_can_access_any_customer_profile(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)
    admin = await add_user(db_session, role=UserRole.ADMIN)

    result = await get_customer_for_user(db_session, admin, customer.id)

    assert result.id == customer.id


async def test_technician_cannot_access_raw_customer_profile(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)
    technician_user, _ = await add_technician(db_session)

    with pytest.raises(AccessDeniedError):
        await get_customer_for_user(
            db_session,
            technician_user,
            customer.id,
        )


async def test_customer_can_access_own_work_order(
    db_session: AsyncSession,
) -> None:
    user, customer = await add_customer(db_session)
    _, _, work_order = await add_work_order(db_session, customer)

    result = await get_work_order_for_user(
        db_session,
        user,
        work_order.id,
    )

    assert result.id == work_order.id


async def test_customer_cannot_access_other_work_order(
    db_session: AsyncSession,
) -> None:
    _, other_customer = await add_customer(db_session)
    _, _, other_work_order = await add_work_order(
        db_session,
        other_customer,
    )
    user, _ = await add_customer(db_session)

    with pytest.raises(AccessDeniedError):
        await get_work_order_for_user(
            db_session,
            user,
            other_work_order.id,
        )


async def test_admin_can_access_any_work_order(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)
    _, _, work_order = await add_work_order(db_session, customer)
    admin = await add_user(db_session, role=UserRole.ADMIN)

    result = await get_work_order_for_user(
        db_session,
        admin,
        work_order.id,
    )

    assert result.id == work_order.id


@pytest.mark.parametrize(
    "status",
    [AssignmentStatus.OFFERED, AssignmentStatus.ACCEPTED],
)
async def test_technician_can_access_visible_assignment(
    db_session: AsyncSession,
    status: AssignmentStatus,
) -> None:
    _, customer = await add_customer(db_session)
    _, _, work_order = await add_work_order(db_session, customer)
    technician_user, technician = await add_technician(db_session)
    db_session.add(
        TechnicianAssignment(
            work_order=work_order,
            technician=technician,
            assignment_status=status,
        )
    )
    await db_session.flush()

    result = await get_work_order_for_user(
        db_session,
        technician_user,
        work_order.id,
    )

    assert result.id == work_order.id


@pytest.mark.parametrize(
    "status",
    [
        AssignmentStatus.REJECTED,
        AssignmentStatus.WITHDRAWN,
        AssignmentStatus.EXPIRED,
    ],
)
async def test_technician_cannot_access_hidden_assignment(
    db_session: AsyncSession,
    status: AssignmentStatus,
) -> None:
    _, customer = await add_customer(db_session)
    _, _, work_order = await add_work_order(db_session, customer)
    technician_user, technician = await add_technician(db_session)
    db_session.add(
        TechnicianAssignment(
            work_order=work_order,
            technician=technician,
            assignment_status=status,
        )
    )
    await db_session.flush()

    with pytest.raises(AccessDeniedError):
        await get_work_order_for_user(
            db_session,
            technician_user,
            work_order.id,
        )


async def test_technician_cannot_access_unassigned_work_order(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)
    _, _, work_order = await add_work_order(db_session, customer)
    technician_user, _ = await add_technician(db_session)

    with pytest.raises(AccessDeniedError):
        await get_work_order_for_user(
            db_session,
            technician_user,
            work_order.id,
        )


async def test_customer_scope_only_returns_owned_work_orders(
    db_session: AsyncSession,
) -> None:
    user, customer = await add_customer(db_session)
    _, _, own_work_order = await add_work_order(db_session, customer)
    _, other_customer = await add_customer(db_session)
    await add_work_order(db_session, other_customer)

    result = await db_session.execute(
        scope_work_orders_for_user(user)
    )
    work_orders = result.scalars().all()

    assert [work_order.id for work_order in work_orders] == [
        own_work_order.id
    ]


async def test_technician_scope_only_returns_visible_work_orders(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)
    _, _, visible_work_order = await add_work_order(db_session, customer)
    _, _, hidden_work_order = await add_work_order(db_session, customer)
    technician_user, technician = await add_technician(db_session)
    db_session.add_all(
        [
            TechnicianAssignment(
                work_order=visible_work_order,
                technician=technician,
                assignment_status=AssignmentStatus.ACCEPTED,
            ),
            TechnicianAssignment(
                work_order=hidden_work_order,
                technician=technician,
                assignment_status=AssignmentStatus.REJECTED,
            ),
        ]
    )
    await db_session.flush()

    result = await db_session.execute(
        scope_work_orders_for_user(technician_user)
    )
    work_orders = result.scalars().all()

    assert [work_order.id for work_order in work_orders] == [
        visible_work_order.id
    ]


async def test_admin_scope_returns_all_work_orders(
    db_session: AsyncSession,
) -> None:
    _, customer_a = await add_customer(db_session)
    _, _, work_order_a = await add_work_order(db_session, customer_a)
    _, customer_b = await add_customer(db_session)
    _, _, work_order_b = await add_work_order(db_session, customer_b)
    admin = await add_user(db_session, role=UserRole.ADMIN)

    result = await db_session.execute(
        scope_work_orders_for_user(admin)
    )
    work_orders = result.scalars().all()

    assert {work_order.id for work_order in work_orders} == {
        work_order_a.id,
        work_order_b.id,
    }


async def test_work_order_scope_uses_a_select(
    db_session: AsyncSession,
) -> None:
    user, _ = await add_customer(db_session)

    statement = scope_work_orders_for_user(user)

    assert isinstance(statement, Select)
