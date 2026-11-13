from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WebhookEventStatus
from app.models.webhook_event import WebhookEvent
from app.services.webhooks.idempotency import (
    mark_webhook_event_failed,
    mark_webhook_event_processed,
    register_webhook_event,
)


async def test_webhook_event_is_registered_once(
    migrated_db_session: AsyncSession,
) -> None:
    payload = b'{"event_id": "evt-1"}'

    first = await register_webhook_event(
        migrated_db_session,
        provider="whatsapp",
        external_event_id="evt-1",
        event_type="messages",
        payload=payload,
    )
    await migrated_db_session.commit()

    assert first.is_duplicate is False
    assert first.event.status is WebhookEventStatus.RECEIVED
    assert first.event.payload_sha256 == hashlib.sha256(payload).hexdigest()

    second = await register_webhook_event(
        migrated_db_session,
        provider="whatsapp",
        external_event_id="evt-1",
        event_type="messages",
        payload=payload,
    )
    await migrated_db_session.commit()

    assert second.is_duplicate is True
    assert second.event.id == first.event.id

    count = await migrated_db_session.scalar(
        select(func.count()).select_from(WebhookEvent)
    )
    assert count == 1


async def test_same_external_id_is_scoped_per_provider(
    migrated_db_session: AsyncSession,
) -> None:
    whatsapp = await register_webhook_event(
        migrated_db_session,
        provider="whatsapp",
        external_event_id="shared-id",
        payload=b"one",
    )
    email = await register_webhook_event(
        migrated_db_session,
        provider="email",
        external_event_id="shared-id",
        payload=b"two",
    )
    await migrated_db_session.commit()

    assert whatsapp.is_duplicate is False
    assert email.is_duplicate is False
    assert whatsapp.event.id != email.event.id


async def test_webhook_event_status_can_be_marked(
    migrated_db_session: AsyncSession,
) -> None:
    registration = await register_webhook_event(
        migrated_db_session,
        provider="whatsapp",
        external_event_id="evt-status",
        payload=b"payload",
    )
    await migrated_db_session.commit()

    processed = await mark_webhook_event_processed(
        migrated_db_session,
        registration.event.id,
    )
    await migrated_db_session.commit()

    assert processed is not None
    assert processed.status is WebhookEventStatus.PROCESSED
    assert processed.processed_at is not None
    assert processed.error_message is None

    failed = await mark_webhook_event_failed(
        migrated_db_session,
        registration.event.id,
        "processing failed",
    )
    await migrated_db_session.commit()

    assert failed is not None
    assert failed.status is WebhookEventStatus.FAILED
    assert failed.error_message == "processing failed"


@pytest.mark.parametrize(
    ("provider", "external_event_id"),
    [
        ("   ", "evt-1"),
        ("whatsapp", "   "),
        ("x" * 51, "evt-1"),
        ("whatsapp", "y" * 256),
    ],
)
async def test_invalid_webhook_identity_is_rejected(
    migrated_db_session: AsyncSession,
    provider: str,
    external_event_id: str,
) -> None:
    with pytest.raises(ValueError):
        await register_webhook_event(
            migrated_db_session,
            provider=provider,
            external_event_id=external_event_id,
            payload=b"payload",
        )
