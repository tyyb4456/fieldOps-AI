from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.user import UserMeResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserMeResponse,
    summary="Current authenticated user",
)
async def read_current_user(
    current_user: User = Depends(get_current_user),
) -> UserMeResponse:
    return UserMeResponse(
        id=current_user.id,
        full_name=current_user.full_name,
        email=current_user.email,
        phone=current_user.phone,
        role=current_user.role,
        is_active=current_user.is_active,
        customer_id=(
            current_user.customer.id
            if current_user.customer is not None
            else None
        ),
        technician_id=(
            current_user.technician.id
            if current_user.technician is not None
            else None
        ),
    )
