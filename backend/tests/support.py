from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint
from app.models.customer import Customer
from app.models.equipment import Equipment
from app.models.enums import (
    ComplaintChannel,
    ComplaintStatus,
    Priority,
    UserRole,
)
from app.models.technician import Technician
from app.models.user import User
from tests.conftest import make_clerk_token


_UNSET = object()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token_for(subject: str) -> str:
    return make_clerk_token(sub=subject)


async def seed_customer(
    session: AsyncSession,
    *,
    full_name: str = "Test Customer",
    address: str | None = "12 Test Street",
    preferred_language: str | None = "en",
    is_active: bool = True,
) -> tuple[User, Customer, str]:
    subject = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name=full_name,
        email=f"{uuid.uuid4().hex}@example.com",
        clerk_user_id=subject,
        password_hash=None,
        role=UserRole.CUSTOMER,
        is_active=is_active,
    )
    customer = Customer(
        user=user,
        address=address,
        preferred_language=preferred_language,
    )
    session.add(user)
    await session.commit()
    return user, customer, _token_for(subject)


async def seed_technician(
    session: AsyncSession,
    *,
    full_name: str = "Test Technician",
    is_active: bool = True,
) -> tuple[User, Technician, str]:
    subject = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name=full_name,
        email=f"{uuid.uuid4().hex}@example.com",
        clerk_user_id=subject,
        password_hash=None,
        role=UserRole.TECHNICIAN,
        is_active=is_active,
    )
    technician = Technician(user=user)
    session.add(user)
    await session.commit()
    return user, technician, _token_for(subject)


async def seed_admin(
    session: AsyncSession,
    *,
    full_name: str = "Test Admin",
    is_active: bool = True,
) -> tuple[User, str]:
    subject = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name=full_name,
        email=f"{uuid.uuid4().hex}@example.com",
        clerk_user_id=subject,
        password_hash=None,
        role=UserRole.ADMIN,
        is_active=is_active,
    )
    session.add(user)
    await session.commit()
    return user, _token_for(subject)


async def seed_equipment(
    session: AsyncSession,
    customer: Customer,
    *,
    manufacturer: str = "Acme Solar",
    model: str = "INV-5000",
    serial_number: str | None | object = _UNSET,
    equipment_type: str = "solar_inverter",
    installation_date: date | None = None,
) -> Equipment:
    resolved_serial = (
        uuid.uuid4().hex[:12]
        if serial_number is _UNSET
        else serial_number
    )
    equipment = Equipment(
        customer_id=customer.id,
        manufacturer=manufacturer,
        model=model,
        serial_number=resolved_serial,
        equipment_type=equipment_type,
        installation_date=installation_date,
    )
    session.add(equipment)
    await session.commit()
    return equipment


async def seed_complaint(
    session: AsyncSession,
    customer: Customer,
    *,
    equipment: Equipment | None = None,
    description: str = "The inverter stopped generating power.",
    status: ComplaintStatus = ComplaintStatus.RECEIVED,
    channel: ComplaintChannel = ComplaintChannel.WEB,
) -> Complaint:
    complaint = Complaint(
        customer_id=customer.id,
        equipment_id=equipment.id if equipment is not None else None,
        description=description,
        channel=channel,
        status=status,
        priority=Priority.NORMAL,
    )
    session.add(complaint)
    await session.commit()
    return complaint
