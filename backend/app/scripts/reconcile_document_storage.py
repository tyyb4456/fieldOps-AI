from __future__ import annotations

import argparse
import asyncio
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.db.session import async_session_factory, dispose_engine
from app.models.document import Document
from app.services.documents.storage import (
    DocumentStorage,
    StorageError,
    StorageObjectInfo,
    build_document_storage,
)
from app.services.documents.storage_coordination import (
    STORAGE_OPERATION_LOCK_KEY,
    advisory_lock,
)

logger = logging.getLogger(__name__)

DEFAULT_MIN_AGE_SECONDS = 5 * 60


@dataclass(frozen=True)
class StaleTempFile:
    key: str
    size: int
    age_seconds: float


@dataclass
class ReconciliationReport:
    referenced_count: int = 0
    stored_count: int = 0
    orphans: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    stale_temp: list[StaleTempFile] = field(default_factory=list)
    deleted_orphans: list[str] = field(default_factory=list)
    deleted_temp: list[str] = field(default_factory=list)
    skipped_young: list[str] = field(default_factory=list)
    skipped_referenced: list[str] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)


def _object_info(
    storage: DocumentStorage,
    key: str,
) -> StorageObjectInfo:
    return storage.stat_key(key)


def _collect_infos(
    storage: DocumentStorage,
    keys: list[str],
) -> dict[str, StorageObjectInfo]:
    infos: dict[str, StorageObjectInfo] = {}
    for key in keys:
        try:
            infos[key] = _object_info(storage, key)
        except StorageError as exc:
            logger.warning(
                "Skipping storage entry that could not be inspected",
                extra={"event": "storage_entry_inspect_failed", "key": key},
            )
            logger.debug("Storage inspect failure: %s", exc)
    return infos


async def _is_still_unreferenced(
    session: AsyncSession,
    key: str,
) -> bool:
    result = await session.scalar(
        select(Document.id).where(Document.storage_key == key).limit(1)
    )
    await session.rollback()
    return result is None


async def reconcile(
    session: AsyncSession,
    storage: DocumentStorage,
    *,
    delete_orphans: bool = False,
    delete_stale_temp: bool = False,
    min_age_seconds: int = DEFAULT_MIN_AGE_SECONDS,
    now: float | None = None,
) -> ReconciliationReport:
    """Report and optionally remove storage artifacts.

    Destructive mode requires an explicit flag. The whole run holds a
    PostgreSQL advisory lock shared with uploads, so no upload can be between
    writing its file and committing its database row. Every candidate is
    re-checked against the database and must be older than the minimum age
    before deletion.
    """

    reference_time = time.time() if now is None else now
    report = ReconciliationReport()

    async with advisory_lock(session, STORAGE_OPERATION_LOCK_KEY):
        result = await session.execute(
            select(Document.storage_key).where(Document.storage_key.is_not(None))
        )
        referenced = {key for key in result.scalars() if key}
        # Do not hold a database transaction while walking the filesystem.
        await session.rollback()

        stored_infos = await run_in_threadpool(
            lambda: _collect_infos(
                storage,
                list(storage.iter_keys()),
            )
        )
        temp_infos = await run_in_threadpool(
            lambda: _collect_infos(
                storage,
                list(storage.iter_temp_keys()),
            )
        )

        stored = set(stored_infos)
        orphans = sorted(stored - referenced)
        missing = sorted(referenced - stored)
        stale_temp = [
            StaleTempFile(
                key=info.key,
                size=info.size,
                age_seconds=reference_time - info.modified_at,
            )
            for info in sorted(temp_infos.values(), key=lambda item: item.key)
            if reference_time - info.modified_at >= min_age_seconds
        ]

        report.referenced_count = len(referenced)
        report.stored_count = len(stored)
        report.orphans = orphans
        report.missing = missing
        report.stale_temp = stale_temp

        if delete_orphans:
            for key in orphans:
                if not await _is_still_unreferenced(session, key):
                    report.skipped_referenced.append(key)
                    logger.warning(
                        "Skipping orphan that became referenced",
                        extra={
                            "event": "storage_orphan_now_referenced",
                            "key": key,
                        },
                    )
                    continue

                info = stored_infos[key]
                age = reference_time - info.modified_at
                if age < min_age_seconds:
                    report.skipped_young.append(key)
                    logger.info(
                        "Skipping orphan younger than minimum age",
                        extra={
                            "event": "storage_orphan_too_young",
                            "key": key,
                        },
                    )
                    continue

                try:
                    if await run_in_threadpool(storage.delete, key):
                        report.deleted_orphans.append(key)
                        logger.warning(
                            "Deleted orphaned document file",
                            extra={
                                "event": "storage_orphan_deleted",
                                "key": key,
                            },
                        )
                except StorageError as exc:
                    report.failures.append((key, str(exc)))
                    logger.warning(
                        "Failed to delete orphaned document file",
                        extra={
                            "event": "storage_orphan_delete_failed",
                            "key": key,
                        },
                    )

        if delete_stale_temp:
            for stale in stale_temp:
                try:
                    if await run_in_threadpool(storage.delete, stale.key):
                        report.deleted_temp.append(stale.key)
                        logger.warning(
                            "Deleted stale temporary upload file",
                            extra={
                                "event": "storage_temp_deleted",
                                "key": stale.key,
                            },
                        )
                except StorageError as exc:
                    report.failures.append((stale.key, str(exc)))
                    logger.warning(
                        "Failed to delete stale temporary upload file",
                        extra={
                            "event": "storage_temp_delete_failed",
                            "key": stale.key,
                        },
                    )

    return report


def _print_report(report: ReconciliationReport) -> None:
    print(f"referenced={report.referenced_count} stored={report.stored_count}")
    print(
        f"orphan_files={len(report.orphans)} "
        f"missing_files={len(report.missing)} "
        f"stale_temp_files={len(report.stale_temp)}"
    )
    for key in report.orphans:
        print(f"orphan {key}")
    for key in report.missing:
        print(f"missing {key}")
    for stale in report.stale_temp:
        print(
            f"stale_temp {stale.key} size={stale.size} "
            f"age_seconds={int(stale.age_seconds)}"
        )
    for key in report.deleted_orphans:
        print(f"deleted_orphan {key}")
    for key in report.deleted_temp:
        print(f"deleted_temp {key}")
    for key in report.skipped_young:
        print(f"skipped_young {key}")
    for key in report.skipped_referenced:
        print(f"skipped_referenced {key}")
    for key, message in report.failures:
        print(f"delete_failed {key} {message}")


async def run_reconciliation(
    *,
    delete_orphans: bool,
    delete_stale_temp: bool,
    min_age_seconds: int,
) -> int:
    storage = build_document_storage(settings)
    async with async_session_factory() as session:
        report = await reconcile(
            session,
            storage,
            delete_orphans=delete_orphans,
            delete_stale_temp=delete_stale_temp,
            min_age_seconds=min_age_seconds,
        )
    _print_report(report)
    await dispose_engine()
    return 1 if report.failures else 0


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description=(
            "Report stored document files that are not referenced by the "
            "database, database rows whose stored file is missing, and stale "
            "temporary upload files."
        )
    )
    parser.add_argument(
        "--delete-orphans",
        action="store_true",
        help="Delete unreferenced files after reporting them.",
    )
    parser.add_argument(
        "--delete-stale-temp",
        action="store_true",
        help="Delete stale temporary upload files after reporting them.",
    )
    parser.add_argument(
        "--min-age-seconds",
        type=int,
        default=DEFAULT_MIN_AGE_SECONDS,
        help=(
            "Minimum file age before an orphan or temporary file may be "
            f"deleted (default: {DEFAULT_MIN_AGE_SECONDS})."
        ),
    )
    arguments = parser.parse_args()
    if arguments.min_age_seconds < 0:
        parser.error("--min-age-seconds must not be negative")
    return asyncio.run(
        run_reconciliation(
            delete_orphans=arguments.delete_orphans,
            delete_stale_temp=arguments.delete_stale_temp,
            min_age_seconds=arguments.min_age_seconds,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
