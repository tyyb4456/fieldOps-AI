from __future__ import annotations

import json
import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")

REQUEST_TOO_LARGE_CODE = "request_too_large"
REQUEST_TOO_LARGE_MESSAGE = "Request body exceeds the configured maximum allowed size."


def _header_value(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


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


class RequestBodyLimitMiddleware:
    """Enforce a request-body bound before routing or multipart parsing.

    FastAPI/Starlette parses ``multipart/form-data`` bodies while resolving the
    endpoint, before endpoint-level dependencies such as authentication run.
    This pure-ASGI middleware therefore buffers at most the configured limit
    (plus one chunk for detection) and rejects oversized bodies itself. It never
    forwards an oversized body to the application and never relies on
    ``Content-Length`` being present or truthful.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = settings.max_request_body_bytes
        content_length = _header_value(scope, b"content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = None
            if declared_length is not None and declared_length > limit:
                await self._send_too_large(scope, send)
                return

        buffered = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            buffered.extend(message.get("body", b""))
            if len(buffered) > limit:
                await self._send_too_large(scope, send)
                return
            if not message.get("more_body", False):
                break

        replayed = False
        body = bytes(buffered)

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,
                }
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _send_too_large(self, scope: Scope, send: Send) -> None:
        payload = json.dumps(
            {
                "error": {
                    "code": REQUEST_TOO_LARGE_CODE,
                    "message": REQUEST_TOO_LARGE_MESSAGE,
                }
            }
        ).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode("ascii")),
        ]
        request_id = scope.get("state", {}).get("request_id")
        if request_id:
            headers.append(
                (
                    REQUEST_ID_HEADER.lower().encode("ascii"),
                    str(request_id).encode("ascii"),
                )
            )
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": payload})


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
