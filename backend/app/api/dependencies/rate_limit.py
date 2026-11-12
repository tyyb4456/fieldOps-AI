from __future__ import annotations

from fastapi import Request, status

from app.core.exceptions import AppError
from app.services.shared.rate_limit import (
    RateLimitExceeded,
    enforce_bootstrap_ip_limit,
)


def rate_limited_error(exc: RateLimitExceeded) -> AppError:
    return AppError(
        "Too many authentication requests. Try again later.",
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code="rate_limited",
        headers={"Retry-After": str(exc.retry_after)},
    )


def bootstrap_ip_rate_limit(request: Request) -> None:
    try:
        enforce_bootstrap_ip_limit(request)
    except RateLimitExceeded as exc:
        raise rate_limited_error(exc) from exc
