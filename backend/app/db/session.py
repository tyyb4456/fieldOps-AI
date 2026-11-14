from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=1800,
    connect_args={"timeout": settings.db_connect_timeout},
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def transaction(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    async with session.begin():
        yield session


async def verify_database_connection() -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        logger.warning(
            "Database readiness check failed",
            exc_info=True,
        )
        return False
    return True


async def dispose_engine() -> None:
    await engine.dispose()


async def _run_and_dispose[T](
    coro: Coroutine[Any, Any, T],
    engine_instance: AsyncEngine,
) -> T:
    try:
        return await coro
    finally:
        try:
            await engine_instance.dispose()
        except Exception:
            logger.exception(
                "Failed to dispose the async database engine after a task",
            )


def run_async_task[T](
    coro: Coroutine[Any, Any, T],
    *,
    engine: AsyncEngine,
) -> T:
    """Run one Celery task coroutine and release pooled connections in-loop.

    Celery's synchronous task wrappers call ``asyncio.run()``, which creates
    and closes a new event loop for every delivery. A module-global
    ``AsyncEngine`` retains asyncpg connections that are bound to the loop that
    opened them, so a connection returned to the pool by one task cannot be
    reused by the next task's loop. Disposing the engine inside the same loop
    guarantees the next delivery starts from an empty pool.
    """

    return asyncio.run(_run_and_dispose(coro, engine))
