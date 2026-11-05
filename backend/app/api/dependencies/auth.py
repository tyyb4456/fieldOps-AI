from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.enums import UserRole
from app.models.user import User
from app.services.accounts import (
    AccountConflictError,
    ProfileInvariantError,
    get_or_provision_user,
)
from app.services.clerk_auth import (
    ClerkAuthenticationError,
    ClerkConfigurationError,
    verify_clerk_token,
)

UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


def unauthenticated_error() -> AppError:
    return AppError(
        "Authentication credentials are invalid or missing.",
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="unauthenticated",
        headers=UNAUTHENTICATED_HEADERS,
    )


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    try:
        identity = await run_in_threadpool(verify_clerk_token, request)
    except ClerkConfigurationError as exc:
        raise AppError(
            "Authentication is not configured.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="authentication_unavailable",
        ) from exc
    except ClerkAuthenticationError as exc:
        raise unauthenticated_error() from exc

    try:
        user = await get_or_provision_user(session, identity)
    except AccountConflictError as exc:
        raise AppError(
            "An account with these details already exists. "
            "Contact support to link your identity.",
            status_code=status.HTTP_409_CONFLICT,
            code="account_conflict",
        ) from exc
    except ProfileInvariantError as exc:
        raise AppError(
            "Account configuration is invalid. Contact support.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="account_configuration_error",
        ) from exc

    if not user.is_active:
        raise AppError(
            "This account is inactive.",
            status_code=status.HTTP_403_FORBIDDEN,
            code="account_inactive",
        )

    return user


def require_roles(*roles: UserRole) -> Callable[..., object]:
    async def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in roles:
            raise AppError(
                "You do not have permission to perform this action.",
                status_code=status.HTTP_403_FORBIDDEN,
                code="forbidden",
            )
        return current_user

    return dependency


require_admin_user = require_roles(UserRole.ADMIN)
require_customer_user = require_roles(UserRole.CUSTOMER)
require_technician_user = require_roles(UserRole.TECHNICIAN)
