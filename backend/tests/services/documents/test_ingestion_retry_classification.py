from __future__ import annotations

import uuid

import pytest
from google.api_core.exceptions import (
    ResourceExhausted,
    ServiceUnavailable,
    Unauthenticated,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.models.enums import IngestionStatus
from app.services.documents.document_ingestion import (
    IngestionInProgressError,
    TransientIngestionError,
    _fail_ingestion,
)
from app.services.rag.embeddings import (
    EmbeddingGenerationError,
    TransientEmbeddingError,
)
from app.services.rag.vector_index import (
    TransientVectorIndexError,
    VectorIndexError,
)
from app.services.shared.retry import TransientError, is_transient_error
from app.tasks.documents import _retry_countdown, _should_retry


def _document() -> Document:
    return Document(
        manufacturer="Acme Solar",
        model="INV-5000",
        document_name=f"Manual {uuid.uuid4().hex}",
        version="1.0",
        storage_key=f"documents/{uuid.uuid4().hex}.pdf",
        ingestion_status=IngestionStatus.PROCESSING,
    )


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (ResourceExhausted("quota"), True),
        (ServiceUnavailable("unavailable"), True),
        (Unauthenticated("bad key"), False),
        (ConnectionResetError("reset"), True),
        (TimeoutError("timeout"), True),
        (ValueError("invalid"), False),
        (TransientError("wrapped"), True),
    ],
)
def test_is_transient_error_classification(
    exc: BaseException,
    expected: bool,
) -> None:
    assert is_transient_error(exc) is expected


def test_is_transient_error_inspects_wrapped_causes() -> None:
    try:
        try:
            raise ServiceUnavailable("provider unavailable")
        except ServiceUnavailable as provider_error:
            raise RuntimeError("sdk wrapper") from provider_error
    except RuntimeError as wrapped:
        assert is_transient_error(wrapped) is True


def test_should_retry_only_transient_and_in_progress() -> None:
    assert _should_retry(TransientIngestionError("retry")) is True
    assert _should_retry(IngestionInProgressError("busy")) is True
    assert _should_retry(ResourceExhausted("quota")) is True
    assert _should_retry(Unauthenticated("bad key")) is False
    assert _should_retry(ValueError("invalid")) is False


def test_explicit_transient_wrappers_are_classified_transient() -> None:
    assert is_transient_error(TransientEmbeddingError("quota")) is True
    assert is_transient_error(TransientVectorIndexError("connection lost")) is True
    assert is_transient_error(EmbeddingGenerationError("bad input")) is False
    assert is_transient_error(VectorIndexError("invalid vector")) is False


def test_retry_backoff_respects_configured_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "celery_task_retry_backoff_seconds", 5)
    monkeypatch.setattr(settings, "celery_task_retry_backoff_max_seconds", 20)

    assert [_retry_countdown(retries) for retries in range(5)] == [
        5,
        10,
        20,
        20,
        20,
    ]


async def test_transient_failure_records_error_and_reraises(
    migrated_db_session: AsyncSession,
) -> None:
    document = _document()
    migrated_db_session.add(document)
    await migrated_db_session.commit()

    with pytest.raises(TransientIngestionError):
        await _fail_ingestion(
            migrated_db_session,
            document.id,
            "The document could not be embedded.",
            ServiceUnavailable("provider unavailable"),
        )

    await migrated_db_session.refresh(document)
    assert document.ingestion_status is IngestionStatus.FAILED
    assert document.ingestion_error == "The document could not be embedded."
    assert document.ingestion_started_at is None


async def test_permanent_failure_records_error_without_raising(
    migrated_db_session: AsyncSession,
) -> None:
    document = _document()
    migrated_db_session.add(document)
    await migrated_db_session.commit()

    failed = await _fail_ingestion(
        migrated_db_session,
        document.id,
        "The PDF could not be read.",
        ValueError("bad pdf"),
    )

    assert failed.ingestion_status is IngestionStatus.FAILED
    assert failed.ingestion_error == "The PDF could not be read."
