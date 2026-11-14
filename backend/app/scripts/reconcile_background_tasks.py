from __future__ import annotations

import argparse
import asyncio
import logging
import uuid

from app.core.config import settings
from app.db.session import async_session_factory, dispose_engine
from app.services.tasks.recovery import (
    fail_stale_pending_tasks,
    fail_stale_running_tasks,
    inspect_background_tasks,
)


async def reconcile(
    *,
    stale_after_seconds: int,
    fail_stale: bool,
    fail_stale_running: bool = False,
) -> int:
    async with async_session_factory() as session:
        report = await inspect_background_tasks(
            session,
            stale_after_seconds=stale_after_seconds,
        )
        print(
            f"stale_pending={len(report.stale_pending_tasks)} "
            f"stale_running={len(report.stale_running_tasks)} "
            f"outbox_pending={report.pending_outbox_events} "
            f"outbox_failed={report.failed_outbox_events} "
            f"processing_documents={len(report.processing_documents)}"
        )
        for task_id in report.stale_pending_tasks:
            print(f"stale_pending_task id={task_id}")
        for task_id in report.stale_running_tasks:
            print(f"stale_running_task id={task_id}")
        for document_id in report.processing_documents:
            print(f"processing_document id={document_id}")

        reconciled: tuple[uuid.UUID, ...] = ()
        if fail_stale:
            reconciled = await fail_stale_pending_tasks(
                session,
                stale_after_seconds=stale_after_seconds,
            )
            for task_id in reconciled:
                print(f"reconciled_task id={task_id}")

        if fail_stale_running:
            reconciled_running = await fail_stale_running_tasks(
                session,
                stale_after_seconds=stale_after_seconds,
            )
            for task_id in reconciled_running:
                print(f"reconciled_running_task id={task_id}")

    await dispose_engine()
    return 1 if report.failed_outbox_events else 0


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description=(
            "Inspect background task, outbox and document ingestion state. Use "
            "--fail-stale to fail stale PENDING tasks that no worker started. "
            "Use --fail-stale-running to finalize stale RUNNING workflow "
            "tasks after the safe execution window. A run whose proposal was "
            "already persisted is completed; any other run is failed. Document "
            "ingestion tasks are only reported. Run dispatch_outbox.py to "
            "publish pending outbox events."
        )
    )
    parser.add_argument(
        "--stale-after-seconds",
        type=int,
        default=settings.ingestion_stale_after_seconds,
        help=(
            "Age after which a task is considered stale "
            f"(default: {settings.ingestion_stale_after_seconds})."
        ),
    )
    parser.add_argument(
        "--fail-stale",
        action="store_true",
        help="Fail stale PENDING tasks.",
    )
    parser.add_argument(
        "--fail-stale-running",
        action="store_true",
        help=(
            "Finalize stale RUNNING workflow tasks after the safe execution "
            "window. Persisted proposals complete their run; other runs fail. "
            "Document ingestion tasks are not modified."
        ),
    )
    arguments = parser.parse_args()
    if arguments.stale_after_seconds < 1:
        parser.error("--stale-after-seconds must be positive")
    return asyncio.run(
        reconcile(
            stale_after_seconds=arguments.stale_after_seconds,
            fail_stale=arguments.fail_stale,
            fail_stale_running=arguments.fail_stale_running,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
