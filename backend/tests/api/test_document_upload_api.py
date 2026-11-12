from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.services.documents import documents as document_service
from app.services.documents.storage import LocalFileStorage
from tests.pdf_factory import build_encrypted_pdf, build_pdf
from tests.support import bearer, seed_admin, seed_customer, seed_technician

METADATA = {
    "manufacturer": "Acme Solar",
    "model": "INV-5000",
    "document_name": "INV-5000 Technical Manual",
    "version": "1.0",
}


def _post(
    api_client: Any,
    token: str | None,
    *,
    data: bytes,
    filename: str = "manual.pdf",
    content_type: str = "application/pdf",
    **metadata: object,
) -> Any:
    headers = bearer(token) if token is not None else {}
    return api_client.post(
        "/api/v1/admin/documents",
        headers=headers,
        data={**METADATA, **metadata},
        files={"file": (filename, data, content_type)},
    )


async def test_upload_requires_admin(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    data = build_pdf(["Allowed text"])
    _, _, customer_token = await seed_customer(migrated_db_session)
    _, _, technician_token = await seed_technician(migrated_db_session)

    assert (
        await _post(api_client, None, data=data)
    ).status_code == 401
    for token in (customer_token, technician_token):
        response = await _post(api_client, token, data=data)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"


async def test_upload_rejects_invalid_signature(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)

    response = await _post(
        api_client,
        admin_token,
        data=b"%PDF-1.4\nthis is not a valid pdf",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_document"
    assert list(document_storage.iter_keys()) == []


async def test_upload_rejects_wrong_extension(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)

    response = await _post(
        api_client,
        admin_token,
        data=build_pdf(["Valid body"]),
        filename="manual.txt",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_document"
    assert list(document_storage.iter_keys()) == []


async def test_upload_rejects_misleading_content_type(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)

    response = await _post(
        api_client,
        admin_token,
        data=build_pdf(["Valid body"]),
        content_type="image/png",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_document"
    assert list(document_storage.iter_keys()) == []


async def test_upload_rejects_empty_file(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)

    response = await _post(api_client, admin_token, data=b"")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_document"
    assert list(document_storage.iter_keys()) == []


async def test_upload_rejects_oversized_file(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    monkeypatch.setattr(settings, "max_upload_size_bytes", 100)

    response = await _post(
        api_client,
        admin_token,
        data=build_pdf(["This document is longer than one hundred bytes"]),
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "document_too_large"
    assert list(document_storage.iter_keys()) == []


async def test_upload_rejects_excessive_page_count(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    monkeypatch.setattr(settings, "max_pdf_pages", 2)

    response = await _post(
        api_client,
        admin_token,
        data=build_pdf(["One", "Two", "Three"]),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "document_page_limit"
    assert list(document_storage.iter_keys()) == []


async def test_upload_sanitizes_client_filename(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)

    response = await _post(
        api_client,
        admin_token,
        data=build_pdf(["Safe content"]),
        filename="../../evil.pdf",
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["original_filename"] == "evil.pdf"
    keys = list(document_storage.iter_keys())
    assert len(keys) == 1
    assert "evil" not in keys[0]
    assert ".." not in keys[0]


async def test_upload_compensates_storage_when_database_fails(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)

    async def fail_create(*args: object, **kwargs: object) -> None:
        raise IntegrityError("INSERT", {}, Exception("database failure"))

    monkeypatch.setattr(
        document_service,
        "create_uploaded_document",
        fail_create,
    )

    response = await _post(
        api_client,
        admin_token,
        data=build_pdf(["Valid body"]),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_conflict"
    assert list(document_storage.iter_keys()) == []

    document_count = await migrated_db_session.scalar(
        select(func.count()).select_from(Document)
    )
    assert document_count == 0


async def test_upload_parses_pdf_once(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_community.document_loaders import PyPDFLoader

    _, admin_token = await seed_admin(migrated_db_session)

    original_load = PyPDFLoader.load
    load_calls: list[str] = []

    def counting_load(loader: PyPDFLoader) -> Any:
        load_calls.append(loader.file_path)
        return original_load(loader)

    monkeypatch.setattr(PyPDFLoader, "load", counting_load)

    response = await _post(
        api_client,
        admin_token,
        data=build_pdf(["Single parse content"]),
    )

    assert response.status_code == 201, response.text
    assert len(load_calls) == 1


async def test_upload_removes_stored_file_when_pdf_is_encrypted(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)

    response = await _post(
        api_client,
        admin_token,
        data=build_encrypted_pdf(["Protected content"]),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_document"
    assert list(document_storage.iter_keys()) == []

    document_count = await migrated_db_session.scalar(
        select(func.count()).select_from(Document)
    )
    assert document_count == 0
