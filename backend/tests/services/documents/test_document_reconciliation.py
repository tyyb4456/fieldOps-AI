from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from app.models.document import Document
from app.scripts.reconcile_document_storage import reconcile
from app.services.documents.storage import LocalFileStorage
from app.services.documents.storage_coordination import (
    STORAGE_OPERATION_LOCK_KEY,
    advisory_lock,
)
from tests.pdf_factory import build_pdf


def _document(storage_key: str | None) -> Document:
    return Document(
        manufacturer="Acme",
        model="INV-5000",
        document_name=f"Manual {uuid.uuid4().hex}",
        storage_key=storage_key,
    )


def _save(
    storage: LocalFileStorage,
    key: str,
    data: bytes,
    *,
    age_seconds: float = 0,
) -> None:
    storage.save(key, data)
    if age_seconds:
        timestamp = time.time() - age_seconds
        os.utime(storage.root / key, (timestamp, timestamp))


@asynccontextmanager
async def _new_session(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(
        bind=session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with factory() as new_session:
        yield new_session


async def test_reconcile_reports_missing_referenced_file(
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    key = document_storage.generate_key("missing.pdf")
    migrated_db_session.add(_document(key))
    await migrated_db_session.commit()

    report = await reconcile(migrated_db_session, document_storage)

    assert report.missing == [key]
    assert report.orphans == []


async def test_reconcile_reports_orphan_without_deleting_by_default(
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    key = document_storage.generate_key("orphan.pdf")
    _save(document_storage, key, build_pdf(["Orphan manual"]), age_seconds=3600)

    report = await reconcile(migrated_db_session, document_storage)

    assert report.orphans == [key]
    assert report.deleted_orphans == []
    assert document_storage.exists(key) is True


async def test_reconcile_deletes_orphan_only_with_explicit_flag(
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    key = document_storage.generate_key("orphan.pdf")
    _save(document_storage, key, build_pdf(["Orphan manual"]), age_seconds=3600)

    report = await reconcile(
        migrated_db_session,
        document_storage,
        delete_orphans=True,
        min_age_seconds=0,
    )

    assert report.deleted_orphans == [key]
    assert document_storage.exists(key) is False


async def test_reconcile_never_deletes_referenced_files(
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    key = document_storage.generate_key("manual.pdf")
    _save(document_storage, key, build_pdf(["Referenced manual"]), age_seconds=3600)
    migrated_db_session.add(_document(key))
    await migrated_db_session.commit()

    report = await reconcile(
        migrated_db_session,
        document_storage,
        delete_orphans=True,
        min_age_seconds=0,
    )

    assert key not in report.orphans
    assert report.deleted_orphans == []
    assert document_storage.exists(key) is True


async def test_in_flight_upload_is_protected_from_reconciliation(
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    key = document_storage.generate_key("in-flight.pdf")
    data = build_pdf(["In-flight manual"])

    async with _new_session(migrated_db_session) as reconcile_session:
        async with advisory_lock(
            migrated_db_session,
            STORAGE_OPERATION_LOCK_KEY,
        ):
            _save(document_storage, key, data, age_seconds=3600)
            task = asyncio.create_task(
                reconcile(
                    reconcile_session,
                    document_storage,
                    delete_orphans=True,
                    min_age_seconds=0,
                )
            )
            await asyncio.sleep(0.2)
            assert task.done() is False

            migrated_db_session.add(_document(key))
            await migrated_db_session.commit()

        report = await task

    assert report.deleted_orphans == []
    assert document_storage.exists(key) is True


async def test_reconcile_reports_and_optionally_deletes_stale_temp_files(
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    stale_key = f"{document_storage.generate_key().split('/')[0]}/.upload-stale"
    active_key = f"{document_storage.generate_key().split('/')[0]}/.upload-active"
    _save(document_storage, stale_key, b"stale", age_seconds=7200)
    _save(document_storage, active_key, b"active", age_seconds=0)

    report = await reconcile(
        migrated_db_session,
        document_storage,
        min_age_seconds=3600,
    )

    assert [item.key for item in report.stale_temp] == [stale_key]
    assert document_storage.exists(stale_key) is True
    assert document_storage.exists(active_key) is True

    deleted = await reconcile(
        migrated_db_session,
        document_storage,
        delete_stale_temp=True,
        min_age_seconds=3600,
    )

    assert deleted.deleted_temp == [stale_key]
    assert document_storage.exists(stale_key) is False
    assert document_storage.exists(active_key) is True


async def test_reconcile_ignores_symlinks_and_path_traversal(
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    outside = Path(document_storage.root).parent / "outside-secret.pdf"
    outside.write_bytes(b"private")

    target_dir = document_storage.root / "aa"
    target_dir.mkdir(parents=True, exist_ok=True)
    link = target_dir / "link.pdf"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symbolic links are not permitted on this platform")

    migrated_db_session.add(_document("../outside-secret.pdf"))
    await migrated_db_session.commit()

    report = await reconcile(
        migrated_db_session,
        document_storage,
        delete_orphans=True,
        delete_stale_temp=True,
        min_age_seconds=0,
    )

    assert "aa/link.pdf" not in report.orphans
    assert outside.exists() is True
    assert outside.read_bytes() == b"private"
    assert report.deleted_orphans == []
    assert "aa/link.pdf" not in report.deleted_temp

    stored_keys = list(document_storage.iter_keys())
    assert "aa/link.pdf" not in stored_keys

    references = await migrated_db_session.execute(select(Document.storage_key))
    assert "../outside-secret.pdf" in set(references.scalars())
