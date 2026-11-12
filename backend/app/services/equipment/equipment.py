from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.equipment import Equipment
from app.schemas.equipment.equipment import EquipmentCreate, EquipmentUpdate
from app.services.shared.authorization import (
    AccessDeniedError,
    scope_equipment_for_customer,
)


async def list_equipment(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID | None,
    equipment_type: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Equipment], int]:
    filters = []
    if customer_id is not None:
        filters.append(Equipment.customer_id == customer_id)
    if equipment_type is not None:
        filters.append(Equipment.equipment_type == equipment_type)

    total = await session.scalar(
        select(func.count()).select_from(Equipment).where(*filters)
    )

    statement = (
        select(Equipment)
        .where(*filters)
        .order_by(Equipment.created_at.desc(), Equipment.id.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(statement)
    return list(result.scalars().all()), int(total or 0)


async def get_equipment(
    session: AsyncSession,
    equipment_id: uuid.UUID,
    *,
    customer_id: uuid.UUID | None = None,
) -> Equipment:
    statement = select(Equipment).where(Equipment.id == equipment_id)
    if customer_id is not None:
        statement = statement.where(Equipment.customer_id == customer_id)

    result = await session.execute(statement)
    equipment = result.scalar_one_or_none()
    if equipment is None:
        raise AccessDeniedError("Equipment not found")
    return equipment


async def get_equipment_for_customer(
    session: AsyncSession,
    customer_id: uuid.UUID,
    equipment_id: uuid.UUID,
) -> Equipment:
    result = await session.execute(
        scope_equipment_for_customer(customer_id).where(
            Equipment.id == equipment_id
        )
    )
    equipment = result.scalar_one_or_none()
    if equipment is None:
        raise AccessDeniedError("Equipment not found")
    return equipment


async def create_equipment(
    session: AsyncSession,
    *,
    customer: Customer,
    data: EquipmentCreate,
) -> Equipment:
    equipment = Equipment(
        customer_id=customer.id,
        manufacturer=data.manufacturer,
        model=data.model,
        serial_number=data.serial_number,
        equipment_type=data.equipment_type,
        installation_date=data.installation_date,
    )
    session.add(equipment)
    await session.flush()
    return equipment


async def update_equipment(
    session: AsyncSession,
    equipment: Equipment,
    data: EquipmentUpdate,
) -> Equipment:
    for field in data.model_fields_set:
        setattr(equipment, field, getattr(data, field))

    await session.flush()
    return equipment


async def delete_equipment(
    session: AsyncSession,
    equipment: Equipment,
) -> None:
    await session.delete(equipment)
    await session.flush()
