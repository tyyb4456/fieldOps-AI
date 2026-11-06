from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.dependencies.rate_limit import rate_limited_error
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.user import User
from app.services.accounts import (
    AccountConflictError,
    ProfileInvariantError,
    find_user_by_clerk_id,
    get_or_provision_user,
    validate_profile_invariant,
)
from app.services.clerk_auth import (
    ClerkAuthenticationError,
    ClerkConfigurationError,
    ClerkIdentity,
    verify_clerk_token,
)
from app.services.rate_limit import (
    RateLimitExceeded,
    enforce_bootstrap_subject_limit,
)

logger = logging.getLogger(__name__)

UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


def unauthenticated_error() -> AppError:
    return AppError(
        "Authentication credentials are invalid or missing.",
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="unauthenticated",
        headers=UNAUTHENTICATED_HEADERS,
    )


def account_inactive_error() -> AppError:
    return AppError(
        "This account is inactive.",
        status_code=status.HTTP_403_FORBIDDEN,
        code="account_inactive",
    )


async def get_authenticated_identity(
    request: Request,
) -> ClerkIdentity:
    try:
        return await run_in_threadpool(verify_clerk_token, request)
    except ClerkConfigurationError as exc:
        raise AppError(
            "Authentication is not configured.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="authentication_unavailable",
        ) from exc
    except ClerkAuthenticationError as exc:
        raise unauthenticated_error() from exc
    except Exception as exc:
        # The Clerk verification boundary must not turn unexpected SDK or
        # network failures into a 500 (which would also hide the WWW-
        # Authenticate challenge). Only this boundary is normalized; database
        # and unrelated application errors remain 500 responses.
        logger.warning(
            "Unexpected Clerk authentication failure",
            extra={
                "error_type": type(exc).__name__,
                "path": request.url.path,
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        raise unauthenticated_error() from exc


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Return an existing user without provisioning or modifying records."""
    identity = await get_authenticated_identity(request)
    user = await find_user_by_clerk_id(session, identity.clerk_user_id)
    if user is None:
        raise AppError(
            "No FieldOps account exists for this identity. "
            "Complete account bootstrap first.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="account_not_provisioned",
        )

    if not user.is_active:
        raise account_inactive_error()

    try:
        await validate_profile_invariant(session, user)
    except ProfileInvariantError as exc:
        raise AppError(
            "Account configuration is invalid. Contact support.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="account_configuration_error",
        ) from exc

    return user


async def get_provisioned_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    identity: ClerkIdentity = Depends(get_authenticated_identity),
) -> User:
    """Provision or reconcile the caller's account during bootstrap."""
    try:
        enforce_bootstrap_subject_limit(identity.clerk_user_id)
    except RateLimitExceeded as exc:
        raise rate_limited_error(exc) from exc

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
        raise account_inactive_error()

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


async def get_current_customer(
    current_user: User = Depends(require_customer_user),
) -> Customer:
    """Resolve the authenticated customer's operational profile.

    ``get_current_user`` already validates the role/profile invariant, so a
    missing profile here indicates a corrupted account rather than a normal
    authorization failure.
    """
    customer = current_user.customer
    if customer is None:
        raise AppError(
            "Account configuration is invalid. Contact support.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="account_configuration_error",
        )
    return customer
