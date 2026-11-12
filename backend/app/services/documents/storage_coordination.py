from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

# PostgreSQL transaction-independent advisory locks coordinate work across every
# application process that shares the database. They are released automatically
# when the holding connection closes, including after a process crash.
STORAGE_OPERATION_LOCK_KEY = 0x444F4353544F5245
_INGESTION_LOCK_SALT = b":fieldops:document-ingestion"


def document_ingestion_lock_key(document_id: uuid.UUID) -> int:
    """Derive a stable positive 63-bit advisory-lock key for a document."""

    digest = hashlib.sha256(document_id.bytes + _INGESTION_LOCK_SALT).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF


@asynccontextmanager
async def advisory_lock(
    session: AsyncSession,
    key: int,
    *,
    blocking: bool = True,
) -> AsyncIterator[bool]:
    """Hold a cross-process PostgreSQL advisory lock on a dedicated connection.

    A dedicated connection is used so no database transaction is held while
    filesystem or PDF work executes. The lock is held until the context exits
    and is always released even if the guarded work raises.
    """

    bind = session.bind
    if not isinstance(bind, AsyncEngine):
        raise TypeError(
            "Advisory locking requires a session bound to an async engine"
        )

    async with bind.connect() as connection:
        acquired = True
        if blocking:
            await connection.execute(
                text("SELECT pg_advisory_lock(:key)"),
                {"key": key},
            )
        else:
            result = await connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": key},
            )
            acquired = bool(result.scalar())
        # End the implicit transaction; session-level advisory locks survive.
        await connection.commit()

        try:
            yield acquired
        finally:
            if acquired:
                try:
                    await connection.execute(
                        text("SELECT pg_advisory_unlock(:key)"),
                        {"key": key},
                    )
                    await connection.commit()
                except Exception:  # noqa: BLE001
                    # Closing the connection releases the lock regardless.
                    await connection.rollback()
