from __future__ import annotations

from app.models.user import User
from app.schemas.user import UserMeResponse


def user_me_response(user: User) -> UserMeResponse:
    return UserMeResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        is_active=user.is_active,
        customer_id=(
            user.customer.id if user.customer is not None else None
        ),
        technician_id=(
            user.technician.id if user.technician is not None else None
        ),
    )
