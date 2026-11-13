from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import OutboxEventStatus
from app.models.outbox_event import OutboxEvent

logger = logging.getLogger(__name__)

MAX_LAST_ERROR_LENGTH = 2000


@dataclass(frozen=True)
class OutboxDispatchResult:
    pending: int
    published: int
    failed: int


def create_outbox_event(
    *,
    event_type: str,
    payload: dict[str, Any],
) -> OutboxEvent:
    return OutboxEvent(
        event_type=event_type,
        payload=payload,
        status=OutboxEventStatus.PENDING,
    )


def _publish_outbox_event(event: OutboxEvent) -> None:
    from app.celery_app import celery_app

    payload = event.payload
    celery_app.send_task(
        event.event_type,
        args=[str(payload["document_id"]), str(payload["background_task_id"])],
        task_id=str(payload["celery_task_id"]),
    )


def _safe_error(exc: BaseException) -> str:
    message = str(exc) or type(exc).__name__
    return message[:MAX_LAST_ERROR_LENGTH]


def _record_publication_failure(event: OutboxEvent, exc: BaseException) -> bool:
    """Record a failed publication and return True when the event is terminal."""

    event.attempts += 1
    event.last_error = _safe_error(exc)
    if event.attempts >= settings.celery_outbox_max_publish_attempts:
        event.status = OutboxEventStatus.FAILED
        logger.error(
            "Outbox event exhausted publication attempts",
            extra={
                "event": "outbox_event_publish_failed",
                "outbox_event_id": str(event.id),
                "event_type": event.event_type,
                "attempts": event.attempts,
                "error_type": type(exc).__name__,
            },
        )
        return True
    logger.warning(
        "Outbox event publication failed",
        extra={
            "event": "outbox_event_publish_retry_scheduled",
            "outbox_event_id": str(event.id),
            "event_type": event.event_type,
            "attempts": event.attempts,
            "error_type": type(exc).__name__,
        },
    )
    return False


def _mark_published(event: OutboxEvent) -> None:
    event.status = OutboxEventStatus.PUBLISHED
    event.published_at = datetime.now(UTC)
    event.attempts += 1
    event.last_error = None


async def dispatch_outbox_event(
    session: AsyncSession,
    event_id: uuid.UUID,
) -> bool:
    """Publish one pending outbox event and mark it published on success.

    Returns True when the event was published by this call. A publication
    failure leaves the event pending for a later dispatch unless the bounded
    attempt limit has been reached.
    """

    statement = (
        select(OutboxEvent)
        .where(OutboxEvent.id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    event = (await session.execute(statement)).scalar_one_or_none()
    if event is None or event.status is not OutboxEventStatus.PENDING:
        return False

    try:
        _publish_outbox_event(event)
    except Exception as exc:  # noqa: BLE001 - broker failures are classified below
        _record_publication_failure(event, exc)
        await session.commit()
        return False

    _mark_published(event)
    await session.commit()
    return True


async def dispatch_pending_outbox_events(
    session: AsyncSession,
    *,
    limit: int | None = None,
) -> OutboxDispatchResult:
    """Publish pending outbox events under a bounded, concurrency-safe claim.

    Rows are claimed with ``FOR UPDATE SKIP LOCKED`` so concurrent dispatchers
    cannot publish the same event. A crash before the final commit leaves every
    claimed event pending, so the next dispatcher run retries them.
    """

    resolved_limit = limit or settings.celery_outbox_dispatch_limit
    statement = (
        select(OutboxEvent)
        .where(OutboxEvent.status == OutboxEventStatus.PENDING)
        .order_by(OutboxEvent.created_at.asc(), OutboxEvent.id.asc())
        .limit(resolved_limit)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    events = list((await session.execute(statement)).scalars().all())

    published = 0
    failed = 0
    for event in events:
        try:
            _publish_outbox_event(event)
        except Exception as exc:  # noqa: BLE001 - broker failures are classified below
            if _record_publication_failure(event, exc):
                failed += 1
        else:
            _mark_published(event)
            published += 1

    await session.commit()

    remaining = await session.scalar(
        select(func.count())
        .select_from(OutboxEvent)
        .where(OutboxEvent.status == OutboxEventStatus.PENDING)
    )
    return OutboxDispatchResult(
        pending=int(remaining or 0),
        published=published,
        failed=failed,
    )


__all__ = [
    "OutboxDispatchResult",
    "create_outbox_event",
    "dispatch_outbox_event",
    "dispatch_pending_outbox_events",
]
