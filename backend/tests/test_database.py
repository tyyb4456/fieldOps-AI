from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import session as session_module

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


class _FakeConnection:
    async def execute(self, statement: object) -> None:
        return None

    async def __aenter__(self) -> _FakeConnection:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _HealthyEngine:
    def connect(self) -> _FakeConnection:
        return _FakeConnection()


class _UnavailableEngine:
    def connect(self) -> _FakeConnection:
        raise OSError("database refused the connection")


async def test_database_check_succeeds_with_working_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_module, "engine", _HealthyEngine())

    assert await session_module.verify_database_connection() is True


async def test_database_check_returns_false_when_connection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_module, "engine", _UnavailableEngine())

    assert await session_module.verify_database_connection() is False


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not configured",
)
async def test_real_postgresql_connectivity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            assert result.scalar_one() == 1

        monkeypatch.setattr(session_module, "engine", engine)
        assert await session_module.verify_database_connection() is True
    finally:
        await engine.dispose()
