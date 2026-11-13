from __future__ import annotations

import argparse
import asyncio
import logging

from app.core.config import settings
from app.db.session import async_session_factory, dispose_engine
from app.services.tasks.outbox import dispatch_pending_outbox_events

logger = logging.getLogger(__name__)


async def dispatch(limit: int) -> int:
    async with async_session_factory() as session:
        result = await dispatch_pending_outbox_events(session, limit=limit)

    print(
        f"outbox_dispatch published={result.published} "
        f"failed={result.failed} pending={result.pending}"
    )
    await dispose_engine()
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description=(
            "Publish pending transactional outbox events to the Redis/Celery "
            "broker. Events are claimed with FOR UPDATE SKIP LOCKED so multiple "
            "dispatchers can run concurrently."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=settings.celery_outbox_dispatch_limit,
        help=(
            "Maximum number of pending events to process per run "
            f"(default: {settings.celery_outbox_dispatch_limit})."
        ),
    )
    arguments = parser.parse_args()
    if arguments.limit < 1:
        parser.error("--limit must be positive")
    return asyncio.run(dispatch(arguments.limit))


if __name__ == "__main__":
    raise SystemExit(main())
