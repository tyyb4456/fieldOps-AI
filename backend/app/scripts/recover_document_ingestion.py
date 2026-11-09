from __future__ import annotations

import argparse
import asyncio
import logging
import uuid

from app.core.config import settings
from app.db.session import async_session_factory, dispose_engine
from app.services.authorization import AccessDeniedError
from app.services.document_ingestion import (
    DocumentRecoveryError,
    recover_stale_processing_document,
)

logger = logging.getLogger(__name__)


async def recover(
    document_id: uuid.UUID,
    *,
    stale_after_seconds: int,
    force_unknown_age: bool,
) -> int:
    async with async_session_factory() as session:
        try:
            document = await recover_stale_processing_document(
                session,
                document_id,
                stale_after_seconds=stale_after_seconds,
                force_unknown_age=force_unknown_age,
            )
        except DocumentRecoveryError as exc:
            print(f"recovery_refused {exc.code}: {exc.message}")
            return 2
        except AccessDeniedError:
            print("recovery_refused not_found: Document not found.")
            return 2

    print(
        f"recovered document_id={document.id} "
        f"status={document.ingestion_status.value} "
        f"is_active={document.is_active}"
    )
    await dispose_engine()
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description=(
            "Recover a document stuck in PROCESSING after an interrupted "
            "ingestion. The document becomes FAILED and stays inactive; it "
            "must be re-ingested and explicitly re-activated afterwards."
        )
    )
    parser.add_argument(
        "--document-id",
        type=uuid.UUID,
        required=True,
        help="Document UUID to recover.",
    )
    parser.add_argument(
        "--stale-after-seconds",
        type=int,
        default=settings.ingestion_stale_after_seconds,
        help=(
            "Minimum age of the ingestion before it is considered stale "
            f"(default: {settings.ingestion_stale_after_seconds})."
        ),
    )
    parser.add_argument(
        "--force-unknown-age",
        action="store_true",
        help=(
            "Allow recovery when no ingestion start time was recorded. Only "
            "use this when no ingestion process can still be running for the "
            "document."
        ),
    )
    arguments = parser.parse_args()
    if arguments.stale_after_seconds < 1:
        parser.error("--stale-after-seconds must be positive")
    return asyncio.run(
        recover(
            arguments.document_id,
            stale_after_seconds=arguments.stale_after_seconds,
            force_unknown_age=arguments.force_unknown_age,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
