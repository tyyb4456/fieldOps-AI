from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://fieldops:fieldops@localhost:5432/fieldops_test",
)

os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "false"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["LOG_LEVEL"] = "WARNING"

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class MigrationDatabase:
    url: str
    config: Config
    name: str


def _sync_url(url: str) -> URL:
    return make_url(url).set(drivername="postgresql+psycopg2")


def _alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.attributes["sqlalchemy_url"] = database_url
    return config


@contextmanager
def _temporary_database() -> Iterator[MigrationDatabase]:
    base_url = make_url(TEST_DATABASE_URL)
    maintenance_url = base_url.set(
        drivername="postgresql+psycopg2",
        database="postgres",
    )

    try:
        admin_engine = create_engine(
            maintenance_url,
            isolation_level="AUTOCOMMIT",
            pool_pre_ping=True,
        )
        with admin_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL test server is unavailable: {exc}")

    database_name = f"fieldops_test_{uuid.uuid4().hex[:12]}"
    target_url = base_url.set(database=database_name)

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    config = _alembic_config(
        target_url.render_as_string(hide_password=False)
    )

    try:
        yield MigrationDatabase(
            url=target_url.render_as_string(hide_password=False),
            config=config,
            name=database_name,
        )
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name "
                    "AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(
                text(f'DROP DATABASE IF EXISTS "{database_name}"')
            )
        admin_engine.dispose()


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[MigrationDatabase]:
    with _temporary_database() as database:
        command.upgrade(database.config, "head")
        yield database


@pytest.fixture()
def empty_migration_database() -> Iterator[MigrationDatabase]:
    with _temporary_database() as database:
        yield database


@pytest_asyncio.fixture
async def db_session(
    migrated_database: MigrationDatabase,
) -> AsyncSession:
    engine = create_async_engine(
        migrated_database.url,
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    try:
        async with session_factory() as session:
            yield session
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_dependency_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()
