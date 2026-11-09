from __future__ import annotations

import json
from typing import Any

import pytest
from app.core.config import settings
from app.core.middleware import RequestBodyLimitMiddleware
from starlette.types import Message, Scope, Send


class _Recorder:
    def __init__(self) -> None:
        self.sent: list[Message] = []
        self.received_bytes = 0
        self.receive_calls = 0

    async def send(self, message: Message) -> None:
        self.sent.append(message)

    async def receive_from(self, messages: list[Message]) -> Any:
        async def receive() -> Message:
            self.receive_calls += 1
            if not messages:
                return {"type": "http.disconnect"}
            message = messages.pop(0)
            self.received_bytes += len(message.get("body", b""))
            return message

        return receive


async def _invoke(
    middleware: RequestBodyLimitMiddleware,
    *,
    headers: dict[str, str],
    messages: list[Message],
    path: str = "/api/v1/admin/documents",
) -> tuple[_Recorder, list[bytes], bool]:
    recorder = _Recorder()
    received_bodies: list[bytes] = []
    app_called = False

    async def application(
        scope: Scope,
        receive: Any,
        send: Send,
    ) -> None:
        nonlocal app_called
        app_called = True
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            received_bodies.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    middleware.app = application
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in headers.items()
        ],
        "state": {},
    }
    receive = await recorder.receive_from(messages)
    await middleware(scope, receive, recorder.send)
    return recorder, received_bodies, app_called


def _status(recorder: _Recorder) -> int:
    start = next(
        message for message in recorder.sent if message["type"] == "http.response.start"
    )
    return int(start["status"])


def _payload(recorder: _Recorder) -> dict[str, Any]:
    body = b"".join(
        message.get("body", b"")
        for message in recorder.sent
        if message["type"] == "http.response.body"
    )
    return json.loads(body)


@pytest.fixture(autouse=True)
def _small_request_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_upload_size_bytes", 100)
    monkeypatch.setattr(settings, "request_body_overhead_bytes", 0)


async def test_oversized_content_length_rejected_before_app_and_parsing() -> None:
    middleware = RequestBodyLimitMiddleware(app=None)  # type: ignore[arg-type]
    recorder, _, app_called = await _invoke(
        middleware,
        headers={"content-length": "101"},
        messages=[{"type": "http.request", "body": b"x" * 101, "more_body": False}],
    )

    assert app_called is False
    assert recorder.receive_calls == 0
    assert recorder.received_bytes == 0
    assert _status(recorder) == 413
    assert _payload(recorder)["error"]["code"] == "request_too_large"


async def test_oversized_chunked_body_without_content_length_is_bounded() -> None:
    middleware = RequestBodyLimitMiddleware(app=None)  # type: ignore[arg-type]
    recorder, _, app_called = await _invoke(
        middleware,
        headers={},
        messages=[
            {"type": "http.request", "body": b"a" * 60, "more_body": True},
            {"type": "http.request", "body": b"b" * 60, "more_body": True},
            {"type": "http.request", "body": b"c" * 60, "more_body": False},
        ],
    )

    assert app_called is False
    assert _status(recorder) == 413
    # Only enough bytes to detect the limit were consumed, not the full body.
    assert recorder.received_bytes == 120
    assert recorder.received_bytes < 180


async def test_body_within_limit_is_replayed_intact() -> None:
    middleware = RequestBodyLimitMiddleware(app=None)  # type: ignore[arg-type]
    recorder, received_bodies, app_called = await _invoke(
        middleware,
        headers={},
        messages=[
            {"type": "http.request", "body": b"hello ", "more_body": True},
            {"type": "http.request", "body": b"world", "more_body": False},
        ],
    )

    assert app_called is True
    assert _status(recorder) == 200
    assert b"".join(received_bodies) == b"hello world"


async def test_unauthenticated_oversized_request_cannot_buffer_unbounded() -> None:
    middleware = RequestBodyLimitMiddleware(app=None)  # type: ignore[arg-type]
    recorder, _, app_called = await _invoke(
        middleware,
        headers={"content-type": "multipart/form-data; boundary=x"},
        messages=[
            {"type": "http.request", "body": b"z" * 70, "more_body": True},
            {"type": "http.request", "body": b"z" * 70, "more_body": False},
        ],
    )

    assert app_called is False
    assert _status(recorder) == 413
    assert recorder.received_bytes == 140


async def test_other_api_requests_are_unaffected(api_client: Any) -> None:
    liveness = await api_client.get("/api/v1/health/live")
    assert liveness.status_code == 200

    bootstrap = await api_client.post("/api/v1/auth/bootstrap", json={})
    assert bootstrap.status_code == 401
