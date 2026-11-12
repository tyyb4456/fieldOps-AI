from __future__ import annotations

from typing import TYPE_CHECKING, Self

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import session as session_module

if TYPE_CHECKING:
    from tests.conftest import MigrationDatabase


class _FakeConnection:
    async def execute(self, statement: object) -> None:
        return None

    async def __aenter__(self) -> Self:
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


async def test_real_postgresql_connectivity(
    monkeypatch: pytest.MonkeyPatch,
    migrated_database: MigrationDatabase,
) -> None:
    engine = create_async_engine(
        migrated_database.url,
        pool_pre_ping=True,
    )
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            assert result.scalar_one() == 1

        monkeypatch.setattr(session_module, "engine", engine)
        assert await session_module.verify_database_connection() is True
    finally:
        await engine.dispose()
