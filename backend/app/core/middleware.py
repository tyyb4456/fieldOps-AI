from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def resolve_request_id(value: str | None) -> str:
    if (
        value
        and len(value) <= MAX_REQUEST_ID_LENGTH
        and REQUEST_ID_PATTERN.fullmatch(value)
    ):
        return value
    return uuid.uuid4().hex


def _log_request(
    request: Request,
    request_id: str,
    status_code: int,
    duration_ms: float,
) -> None:
    logger.info(
        "%s %s %s %.2fms",
        request.method,
        request.url.path,
        status_code,
        duration_ms,
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": duration_ms,
        },
    )


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id

        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            _log_request(request, request_id, 500, duration_ms)
            raise

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        _log_request(request, request_id, response.status_code, duration_ms)

        return response
