from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

import pytest
from langchain_core.documents import Document as LangChainDocument
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import IngestionStatus
from app.services.documents.document_ingestion import (
    INGESTION_ERROR_EMBEDDING,
    INGESTION_ERROR_EMPTY,
    INGESTION_ERROR_INTEGRITY,
    PdfValidationError,
    load_pdf_documents,
    normalize_extracted_text,
    split_page_documents,
)
from app.services.documents.storage import LocalFileStorage
from app.services.rag.vector_index import VectorIndexError
from tests.pdf_factory import build_encrypted_pdf, build_pdf
from tests.support import bearer, seed_admin

METADATA = {
    "manufacturer": "Acme Solar",
    "model": "INV-5000",
    "document_name": "INV-5000 Technical Manual",
    "version": "1.0",
}


def _upload(
    api_client: Any,
    token: str,
    pages: list[str],
    **overrides: object,
) -> Any:
    return api_client.post(
        "/api/v1/admin/documents",
        headers=bearer(token),
        data={**METADATA, **overrides},
        files={"file": ("manual.pdf", build_pdf(pages), "application/pdf")},
    )


def _write_pdf(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / f"{uuid.uuid4().hex}.pdf"
    path.write_bytes(data)
    return path


def _page_document(page: int, text: str) -> LangChainDocument:
    return LangChainDocument(page_content=text, metadata={"page": page})


def test_loader_loads_single_page_with_page_metadata(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, build_pdf(["Manual text"]))

    documents = load_pdf_documents(path, max_pages=10)

    assert len(documents) == 1
    assert documents[0].page_content == "Manual text"
    assert documents[0].metadata["page"] == 0
    assert documents[0].metadata["page_label"] == "1"


def test_loader_preserves_multi_page_attribution_and_empty_pages(
    tmp_path: Path,
) -> None:
    path = _write_pdf(tmp_path, build_pdf(["Page one", "", "Page three"]))

    documents = load_pdf_documents(path, max_pages=10)

    assert [(doc.metadata["page"], doc.page_content) for doc in documents] == [
        (0, "Page one"),
        (1, ""),
        (2, "Page three"),
    ]


def test_loader_rejects_invalid_pdf(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, b"%PDF-1.4\ncorrupt")

    with pytest.raises(PdfValidationError):
        load_pdf_documents(path, max_pages=10)


def test_loader_rejects_encrypted_pdf(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, build_encrypted_pdf(["Secret page"]))

    with pytest.raises(PdfValidationError) as error:
        load_pdf_documents(path, max_pages=10)

    assert "Encrypted" in error.value.message


def test_loader_rejects_zero_page_pdf(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, build_pdf([]))

    with pytest.raises(PdfValidationError) as error:
        load_pdf_documents(path, max_pages=10)

    assert "does not contain any pages" in error.value.message


def test_loader_enforces_maximum_page_count(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, build_pdf(["One", "Two", "Three"]))

    with pytest.raises(PdfValidationError) as error:
        load_pdf_documents(path, max_pages=2)

    assert error.value.code == "document_page_limit"


def test_loader_invokes_pypdf_once_per_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_community.document_loaders import PyPDFLoader

    path = _write_pdf(tmp_path, build_pdf(["Manual text"]))
    calls: list[int] = []
    original_load = PyPDFLoader.load

    def counting_load(loader: PyPDFLoader) -> list[LangChainDocument]:
        calls.append(1)
        return original_load(loader)

    monkeypatch.setattr(PyPDFLoader, "load", counting_load)

    load_pdf_documents(path, max_pages=10)

    assert len(calls) == 1


def test_splitter_respects_configured_size_and_overlap() -> None:
    text = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    chunks = split_page_documents(
        [_page_document(0, text)],
        chunk_size=10,
        chunk_overlap=3,
    )

    assert [chunk.char_start for chunk in chunks] == [0, 7, 14, 21, 28]
    assert [chunk.char_end for chunk in chunks] == [10, 17, 24, 31, 36]
    for chunk in chunks:
        assert len(chunk.content) <= 10
        assert chunk.content == text[chunk.char_start : chunk.char_end]
        assert chunk.content.strip()


def test_splitter_preserves_page_order_and_skips_empty_pages() -> None:
    chunks = split_page_documents(
        [
            _page_document(0, "First page"),
            _page_document(1, ""),
            _page_document(2, "   "),
            _page_document(3, "Fourth page"),
        ],
        chunk_size=100,
        chunk_overlap=10,
    )

    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert [chunk.page_number for chunk in chunks] == [1, 4]


def test_splitter_keeps_page_local_offsets_for_identical_text() -> None:
    chunks = split_page_documents(
        [
            _page_document(0, "Same text"),
            _page_document(1, "Same text"),
        ],
        chunk_size=100,
        chunk_overlap=10,
    )

    assert [
        (chunk.page_number, chunk.char_start, chunk.char_end)
        for chunk in chunks
    ] == [(1, 0, 9), (2, 0, 9)]


def test_splitter_offsets_are_valid_for_repeated_paragraphs() -> None:
    text = ("Amplifier manual. " * 40).strip()

    chunks = split_page_documents(
        [_page_document(0, text)],
        chunk_size=64,
        chunk_overlap=16,
    )

    assert chunks
    for chunk in chunks:
        assert 0 <= chunk.char_start < chunk.char_end <= len(text)
        assert text[chunk.char_start : chunk.char_end] == chunk.content
    starts = [chunk.char_start for chunk in chunks]
    assert starts == sorted(starts)


def test_splitter_is_paragraph_aware() -> None:
    text = "First paragraph.\n\nSecond paragraph."

    chunks = split_page_documents(
        [_page_document(0, text)],
        chunk_size=20,
        chunk_overlap=0,
    )

    assert [chunk.content for chunk in chunks] == [
        "First paragraph.",
        "Second paragraph.",
    ]


def test_splitter_returns_no_chunks_for_empty_pages() -> None:
    chunks = split_page_documents(
        [_page_document(0, ""), _page_document(1, "   ")],
        chunk_size=100,
        chunk_overlap=10,
    )

    assert chunks == []


def test_splitter_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError):
        split_page_documents(
            [_page_document(0, "text")],
            chunk_size=10,
            chunk_overlap=10,
        )


def test_text_normalization_is_conservative() -> None:
    text = "  Line one\r\nLine two\r\n\r\n\r\n\tValue\x00  "

    normalized = normalize_extracted_text(text)

    assert normalized == "Line one\nLine two\n\n\tValue"


async def test_uploaded_empty_text_pdf_is_stored_as_failed(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)

    response = await _upload(api_client, admin_token, ["", "   "])

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["ingestion_status"] == "failed"
    assert body["ingestion_error"] == INGESTION_ERROR_EMPTY
    assert body["is_active"] is False

    chunks = await migrated_db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == body["id"])
    )
    assert list(chunks.scalars()) == []


async def test_chunk_metadata_tracks_pages_and_offsets(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    response = await _upload(
        api_client,
        admin_token,
        ["Page one text", "", "Page three text"],
    )
    assert response.status_code == 202, response.text
    document_id = response.json()["id"]

    chunks = await migrated_db_session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    stored = list(chunks.scalars())

    assert [chunk.page_number for chunk in stored] == [1, 3]
    assert [chunk.chunk_index for chunk in stored] == [0, 1]
    assert stored[0].content == "Page one text"
    assert stored[0].chunk_metadata == {
        "char_start": 0,
        "char_end": len("Page one text"),
        "ingestion_version": "1",
    }


async def test_embedding_failure_marks_ingestion_failed(
    api_client: Any,
    migrated_db_session: AsyncSession,
    vector_index: Any,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    vector_index.add_error = VectorIndexError("embedding provider unavailable")

    response = await _upload(api_client, admin_token, ["Manual text"])

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["ingestion_status"] == "failed"
    assert body["ingestion_error"] == INGESTION_ERROR_EMBEDDING
    assert body["is_active"] is False

    chunks = await migrated_db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == body["id"])
    )
    assert list(chunks.scalars()) == []

    activated = await api_client.post(
        f"/api/v1/admin/documents/{body['id']}/activate",
        headers=bearer(admin_token),
    )
    assert activated.status_code == 409


async def test_reingestion_atomically_replaces_chunks(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
    vector_index: Any,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    uploaded = await _upload(api_client, admin_token, ["Original manual text"])
    assert uploaded.status_code == 202, uploaded.text
    document_id = uploaded.json()["id"]

    activated = await api_client.post(
        f"/api/v1/admin/documents/{document_id}/activate",
        headers=bearer(admin_token),
    )
    assert activated.status_code == 200, activated.text

    storage_key = await migrated_db_session.scalar(
        select(Document.storage_key).where(Document.id == document_id)
    )
    assert storage_key is not None
    replacement = build_pdf(["Replacement manual text"])
    document_storage.save(
        storage_key,
        replacement,
        overwrite=True,
    )
    document = await migrated_db_session.get(Document, document_id)
    assert document is not None
    document.byte_size = len(replacement)
    document.checksum_sha256 = hashlib.sha256(replacement).hexdigest()
    await migrated_db_session.commit()

    response = await api_client.post(
        f"/api/v1/admin/documents/{document_id}/ingest",
        headers=bearer(admin_token),
    )

    assert response.status_code == 202, response.text
    assert response.json()["ingestion_status"] == "ready"
    assert response.json()["is_active"] is False

    chunks = await migrated_db_session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    contents = [chunk.content for chunk in chunks.scalars()]
    assert contents == ["Replacement manual text"]

    assert len(vector_index.added_chunks) == 2
    indexed_document_id, indexed_chunks = vector_index.added_chunks[-1]
    assert str(indexed_document_id) == document_id
    assert [chunk.content for chunk in indexed_chunks] == [
        "Replacement manual text"
    ]


async def test_reingestion_parses_pdf_once(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
    monkeypatch: Any,
) -> None:
    from langchain_community.document_loaders import PyPDFLoader

    _, admin_token = await seed_admin(migrated_db_session)
    uploaded = await _upload(api_client, admin_token, ["Parse count manual"])
    assert uploaded.status_code == 202, uploaded.text
    document_id = uploaded.json()["id"]

    activated = await api_client.post(
        f"/api/v1/admin/documents/{document_id}/activate",
        headers=bearer(admin_token),
    )
    assert activated.status_code == 200, activated.text

    storage_key = await migrated_db_session.scalar(
        select(Document.storage_key).where(Document.id == document_id)
    )
    assert storage_key is not None
    replacement = build_pdf(["Replacement once"])
    document_storage.save(storage_key, replacement, overwrite=True)
    document = await migrated_db_session.get(Document, document_id)
    assert document is not None
    document.byte_size = len(replacement)
    document.checksum_sha256 = hashlib.sha256(replacement).hexdigest()
    await migrated_db_session.commit()

    original_load = PyPDFLoader.load
    load_calls: list[str] = []

    def counting_load(loader: PyPDFLoader) -> Any:
        load_calls.append(loader.file_path)
        return original_load(loader)

    monkeypatch.setattr(PyPDFLoader, "load", counting_load)

    response = await api_client.post(
        f"/api/v1/admin/documents/{document_id}/ingest",
        headers=bearer(admin_token),
    )

    assert response.status_code == 202, response.text
    assert len(load_calls) == 1


async def test_failed_reingestion_preserves_old_chunks_and_deactivates(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    uploaded = await _upload(api_client, admin_token, ["Stable manual text"])
    assert uploaded.status_code == 202, uploaded.text
    document_id = uploaded.json()["id"]

    activated = await api_client.post(
        f"/api/v1/admin/documents/{document_id}/activate",
        headers=bearer(admin_token),
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["is_active"] is True

    storage_key = await migrated_db_session.scalar(
        select(Document.storage_key).where(Document.id == document_id)
    )
    assert storage_key is not None
    document_storage.save(
        storage_key,
        b"%PDF-1.4\ncorrupt body",
        overwrite=True,
    )

    response = await api_client.post(
        f"/api/v1/admin/documents/{document_id}/ingest",
        headers=bearer(admin_token),
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["ingestion_status"] == "failed"
    assert body["is_active"] is False
    assert body["ingestion_error"] == INGESTION_ERROR_INTEGRITY

    chunks = await migrated_db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    assert [chunk.content for chunk in chunks.scalars()] == ["Stable manual text"]


async def test_failed_replacement_embedding_preserves_previous_chunks(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
    vector_index: Any,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    uploaded = await _upload(api_client, admin_token, ["Stable manual text"])
    assert uploaded.status_code == 202, uploaded.text
    document_id = uploaded.json()["id"]

    activated = await api_client.post(
        f"/api/v1/admin/documents/{document_id}/activate",
        headers=bearer(admin_token),
    )
    assert activated.status_code == 200, activated.text

    original_chunks = await migrated_db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    original = list(original_chunks.scalars())
    assert [chunk.content for chunk in original] == ["Stable manual text"]

    storage_key = await migrated_db_session.scalar(
        select(Document.storage_key).where(Document.id == document_id)
    )
    assert storage_key is not None
    replacement = build_pdf(["Replacement manual text"])
    document_storage.save(storage_key, replacement, overwrite=True)
    document = await migrated_db_session.get(Document, document_id)
    assert document is not None
    document.byte_size = len(replacement)
    document.checksum_sha256 = hashlib.sha256(replacement).hexdigest()
    await migrated_db_session.commit()

    vector_index.embed_error = VectorIndexError("provider unavailable")

    response = await api_client.post(
        f"/api/v1/admin/documents/{document_id}/ingest",
        headers=bearer(admin_token),
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["ingestion_status"] == "failed"
    assert body["is_active"] is False
    assert body["ingestion_error"] == INGESTION_ERROR_EMBEDDING

    chunks = await migrated_db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    stored = list(chunks.scalars())
    assert [chunk.content for chunk in stored] == ["Stable manual text"]
    assert {chunk.id for chunk in stored} == {chunk.id for chunk in original}
    assert all(chunk.is_current for chunk in stored)

    assert len(vector_index.added_chunks) == 1


async def test_concurrent_ingestion_is_rejected(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    uploaded = await _upload(api_client, admin_token, ["Manual text"])
    assert uploaded.status_code == 202, uploaded.text
    document_id = uploaded.json()["id"]

    document = await migrated_db_session.get(Document, document_id)
    assert document is not None
    document.ingestion_status = IngestionStatus.PROCESSING
    await migrated_db_session.commit()

    response = await api_client.post(
        f"/api/v1/admin/documents/{document_id}/ingest",
        headers=bearer(admin_token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ingestion_in_progress"


async def test_missing_stored_file_marks_ingestion_failed(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    uploaded = await _upload(api_client, admin_token, ["Manual text"])
    assert uploaded.status_code == 202, uploaded.text
    document_id = uploaded.json()["id"]

    storage_key = await migrated_db_session.scalar(
        select(Document.storage_key).where(Document.id == document_id)
    )
    assert storage_key is not None
    document_storage.delete(storage_key)

    response = await api_client.post(
        f"/api/v1/admin/documents/{document_id}/ingest",
        headers=bearer(admin_token),
    )

    assert response.status_code == 202, response.text
    assert response.json()["ingestion_status"] == "failed"
    assert "missing or unreadable" in response.json()["ingestion_error"]
