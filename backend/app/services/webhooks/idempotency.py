from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WebhookEventStatus
from app.models.webhook_event import WebhookEvent

MAX_PROVIDER_LENGTH = 50
MAX_EXTERNAL_EVENT_ID_LENGTH = 255
MAX_EVENT_TYPE_LENGTH = 100


@dataclass(frozen=True)
class WebhookRegistration:
    event: WebhookEvent
    is_duplicate: bool


def _required(value: str, field_name: str, max_length: int) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be blank")
    if len(cleaned) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return cleaned


def _optional(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise ValueError(f"event_type must be at most {max_length} characters")
    return cleaned


async def register_webhook_event(
    session: AsyncSession,
    *,
    provider: str,
    external_event_id: str,
    payload: bytes,
    event_type: str | None = None,
) -> WebhookRegistration:
    """Register a provider event exactly once.

    The unique constraint on ``(provider, external_event_id)`` is the source of
    truth, so concurrent duplicate deliveries cannot both create a row. The
    caller commits the surrounding transaction before running side effects.
    """

    normalized_provider = _required(
        provider,
        "provider",
        MAX_PROVIDER_LENGTH,
    )
    normalized_external_id = _required(
        external_event_id,
        "external_event_id",
        MAX_EXTERNAL_EVENT_ID_LENGTH,
    )
    normalized_event_type = _optional(event_type, MAX_EVENT_TYPE_LENGTH)
    payload_sha256 = hashlib.sha256(payload).hexdigest()

    statement = (
        insert(WebhookEvent)
        .values(
            provider=normalized_provider,
            external_event_id=normalized_external_id,
            event_type=normalized_event_type,
            payload_sha256=payload_sha256,
            status=WebhookEventStatus.RECEIVED,
        )
        .on_conflict_do_nothing(
            index_elements=["provider", "external_event_id"],
        )
        .returning(WebhookEvent)
    )
    event = (await session.execute(statement)).scalar_one_or_none()
    if event is not None:
        return WebhookRegistration(event=event, is_duplicate=False)

    existing = (
        await session.execute(
            select(WebhookEvent).where(
                WebhookEvent.provider == normalized_provider,
                WebhookEvent.external_event_id == normalized_external_id,
            )
        )
    ).scalar_one()
    return WebhookRegistration(event=existing, is_duplicate=True)


async def mark_webhook_event_processed(
    session: AsyncSession,
    event_id: uuid.UUID,
) -> WebhookEvent | None:
    event = await session.get(WebhookEvent, event_id)
    if event is None:
        return None
    event.status = WebhookEventStatus.PROCESSED
    event.processed_at = datetime.now(UTC)
    event.error_message = None
    return event


async def mark_webhook_event_failed(
    session: AsyncSession,
    event_id: uuid.UUID,
    error_message: str,
) -> WebhookEvent | None:
    event = await session.get(WebhookEvent, event_id)
    if event is None:
        return None
    event.status = WebhookEventStatus.FAILED
    event.processed_at = datetime.now(UTC)
    event.error_message = error_message[:2000]
    return event


__all__ = [
    "WebhookRegistration",
    "mark_webhook_event_failed",
    "mark_webhook_event_processed",
    "register_webhook_event",
]
