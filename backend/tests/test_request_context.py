from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.main import create_application

GENERATED_REQUEST_ID = re.compile(r"^[0-9a-f]{32}$")


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextmanager
def capture_logs(*logger_names: str) -> Iterator[list[logging.LogRecord]]:
    handler = ListHandler()
    loggers = [logging.getLogger(name) for name in logger_names]
    previous = [(logger.level, logger.propagate) for logger in loggers]

    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

    try:
        yield handler.records
    finally:
        for logger, (level, propagate) in zip(loggers, previous):
            logger.removeHandler(handler)
            logger.setLevel(level)
            logger.propagate = propagate


@pytest.mark.parametrize(
    "request_id",
    [
        "",
        "x" * 5000,
        "bad space",
        "bad\x00id",
    ],
)
def test_invalid_request_ids_are_replaced(
    client: TestClient,
    request_id: str,
) -> None:
    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": request_id},
    )

    generated = response.headers["X-Request-ID"]
    assert generated != request_id
    assert GENERATED_REQUEST_ID.fullmatch(generated)


@pytest.mark.parametrize(
    "request_id",
    [
        "test-request-id",
        "0123456789abcdef0123456789abcdef",
        "trace.id_1:2",
    ],
)
def test_valid_request_ids_are_preserved(
    client: TestClient,
    request_id: str,
) -> None:
    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": request_id},
    )

    assert response.headers["X-Request-ID"] == request_id


def test_unhandled_exception_preserves_request_id_and_logs() -> None:
    application = create_application()

    @application.get("/_audit/boom", include_in_schema=False)
    async def boom() -> None:
        raise RuntimeError(
            "internal detail: postgresql://user:secret@db.example.com/internal"
        )

    with capture_logs("app.request", "app.core.exceptions") as records:
        with TestClient(
            application,
            raise_server_exceptions=False,
        ) as client:
            response = client.get(
                "/_audit/boom",
                headers={"X-Request-ID": "trace-500"},
            )

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "trace-500"
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "An unexpected error occurred.",
        }
    }
    assert "secret" not in response.text
    assert "RuntimeError" not in response.text

    access_records = [
        record
        for record in records
        if record.name == "app.request"
        and getattr(record, "status_code", None) == 500
    ]
    assert access_records
    assert access_records[0].request_id == "trace-500"

    exception_records = [
        record
        for record in records
        if record.name == "app.core.exceptions"
    ]
    assert exception_records
    assert exception_records[0].request_id == "trace-500"
    assert exception_records[0].exc_info is not None


def test_unhandled_exception_generates_request_id_when_invalid() -> None:
    application = create_application()

    @application.get("/_audit/boom", include_in_schema=False)
    async def boom() -> None:
        raise RuntimeError("boom")

    with TestClient(
        application,
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            "/_audit/boom",
            headers={"X-Request-ID": "bad id"},
        )

    assert response.status_code == 500
    assert GENERATED_REQUEST_ID.fullmatch(
        response.headers["X-Request-ID"]
    )
