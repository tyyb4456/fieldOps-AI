from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import get_current_user
from app.api.serializers import user_me_response
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
    return user_me_response(current_user)
