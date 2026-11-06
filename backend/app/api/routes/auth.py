from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import get_provisioned_current_user
from app.api.dependencies.rate_limit import bootstrap_ip_rate_limit
from app.api.serializers import user_me_response
from app.models.user import User
from app.schemas.user import UserMeResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/bootstrap",
    response_model=UserMeResponse,
    summary="Provision or reconcile the current Clerk identity",
    dependencies=[Depends(bootstrap_ip_rate_limit)],
)
async def bootstrap_current_user(
    current_user: User = Depends(get_provisioned_current_user),
) -> UserMeResponse:
    """Idempotently create or update the caller's local account.

    Public bootstrap always creates CUSTOMER accounts. Privileged accounts are
    bound only through the operator-controlled role/linking commands.
    """
    return user_me_response(current_user)
