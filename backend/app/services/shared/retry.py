from __future__ import annotations

import asyncio
import socket

from google.api_core import exceptions as google_exceptions
from redis import exceptions as redis_exceptions
from sqlalchemy import exc as sqlalchemy_exceptions


class TransientError(Exception):
    """Base class for retryable transient failures."""


class PermanentError(Exception):
    """Base class for terminal failures that must not be retried."""


_TRANSIENT_GOOGLE_ERRORS: tuple[type[BaseException], ...] = (
    google_exceptions.ResourceExhausted,
    google_exceptions.TooManyRequests,
    google_exceptions.DeadlineExceeded,
    google_exceptions.ServiceUnavailable,
    google_exceptions.BadGateway,
    google_exceptions.GatewayTimeout,
    google_exceptions.InternalServerError,
    google_exceptions.ServerError,
    google_exceptions.RetryError,
)

_TRANSIENT_CONNECTION_ERRORS: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    TimeoutError,
    ConnectionError,
    ConnectionRefusedError,
    ConnectionResetError,
    ConnectionAbortedError,
    socket.timeout,
    socket.gaierror,
    redis_exceptions.ConnectionError,
    redis_exceptions.TimeoutError,
    sqlalchemy_exceptions.InterfaceError,
    sqlalchemy_exceptions.OperationalError,
    sqlalchemy_exceptions.TimeoutError,
)


def is_transient_error(exc: BaseException) -> bool:
    """Return True when ``exc`` represents a retryable transient failure.

    Provider SDK exceptions, connection failures and database connectivity
    errors are inspected through the exception chain so a failure wrapped by
    an SDK or ORM still receives the correct classification.
    """

    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, TransientError):
            return True
        if isinstance(current, _TRANSIENT_GOOGLE_ERRORS):
            return True
        if isinstance(current, _TRANSIENT_CONNECTION_ERRORS):
            return True
        current = current.__cause__ or current.__context__
    return False


__all__ = [
    "PermanentError",
    "TransientError",
    "is_transient_error",
]
