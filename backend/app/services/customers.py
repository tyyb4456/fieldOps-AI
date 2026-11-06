from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer import Customer
from app.schemas.customer import CustomerUpdate
from app.services.authorization import AccessDeniedError


async def get_customer_for_admin(
    session: AsyncSession,
    customer_id: uuid.UUID,
) -> Customer:
    result = await session.execute(
        select(Customer)
        .options(selectinload(Customer.user))
        .where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise AccessDeniedError("Customer not found")
    return customer


async def update_customer_profile(
    session: AsyncSession,
    customer: Customer,
    data: CustomerUpdate,
) -> Customer:
    """Apply only the customer-owned profile fields present in the request."""
    if "address" in data.model_fields_set:
        customer.address = data.address
    if "preferred_language" in data.model_fields_set:
        customer.preferred_language = data.preferred_language

    await session.flush()
    return customer
