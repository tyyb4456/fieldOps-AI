from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    get_current_customer,
    require_admin_user,
    require_customer_user,
)
from app.api.serializers import customer_profile_response
from app.db.session import get_db_session
from app.models.customer import Customer
from app.models.user import User
from app.schemas.customer import CustomerProfileResponse, CustomerUpdate
from app.services.customers import (
    get_customer_for_admin,
    update_customer_profile,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get(
    "/me",
    response_model=CustomerProfileResponse,
    summary="Current customer's profile",
)
async def read_own_customer_profile(
    current_user: User = Depends(require_customer_user),
    customer: Customer = Depends(get_current_customer),
) -> CustomerProfileResponse:
    return customer_profile_response(customer, current_user)


@router.patch(
    "/me",
    response_model=CustomerProfileResponse,
    summary="Update current customer's profile",
)
async def update_own_customer_profile(
    payload: CustomerUpdate,
    current_user: User = Depends(require_customer_user),
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileResponse:
    updated = await update_customer_profile(session, customer, payload)
    await session.commit()
    await session.refresh(updated)

    logger.info(
        "Customer profile updated",
        extra={
            "event": "customer_profile_updated",
            "actor_id": str(current_user.id),
            "customer_id": str(updated.id),
        },
    )
    return customer_profile_response(updated, current_user)


@router.get(
    "/{customer_id}",
    response_model=CustomerProfileResponse,
    summary="Admin: read any customer profile",
)
async def read_customer_profile_for_admin(
    customer_id: uuid.UUID,
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileResponse:
    customer = await get_customer_for_admin(session, customer_id)
    return customer_profile_response(customer)
