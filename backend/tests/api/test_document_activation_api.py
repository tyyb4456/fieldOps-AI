from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import IngestionStatus
from app.services.documents.storage import LocalFileStorage
from tests.pdf_factory import build_pdf
from tests.support import bearer, seed_admin

METADATA = {
    "manufacturer": "Acme Solar",
    "model": "INV-5000",
    "document_name": "INV-5000 Technical Manual",
    "version": "1.0",
}


def _upload(api_client: Any, token: str) -> Any:
    return api_client.post(
        "/api/v1/admin/documents",
        headers=bearer(token),
        data=METADATA,
        files={
            "file": (
                "manual.pdf",
                build_pdf(["Activation test manual text"]),
                "application/pdf",
            )
        },
    )


async def _seed_ready_document(
    session: AsyncSession,
    storage: LocalFileStorage,
    *,
    with_chunks: bool = True,
    store_file: bool = True,
    storage_metadata: bool = True,
    **overrides: object,
) -> Document:
    key = storage.generate_key("manual.pdf")
    data = build_pdf(["Seed manual text"])
    if store_file:
        storage.save(key, data)

    values: dict[str, object] = {
        **METADATA,
        "ingestion_status": IngestionStatus.READY,
        "is_active": False,
    }
    if storage_metadata:
        values.update(
            storage_key=key,
            original_filename="manual.pdf",
            content_type="application/pdf",
            byte_size=len(data),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
        )
    values.update(overrides)

    document = Document(**values)
    session.add(document)
    await session.commit()
    await session.refresh(document)

    if with_chunks:
        session.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content="Seed manual text",
                page_number=1,
                chunk_metadata={"ingestion_version": "1"},
            )
        )
        await session.commit()

    return document


async def test_admin_activates_and_deactivates_ready_document(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    uploaded = await _upload(api_client, admin_token)
    assert uploaded.status_code == 202, uploaded.text
    document_id = uploaded.json()["id"]
    assert uploaded.json()["is_active"] is False

    activated = await api_client.post(
        f"/api/v1/admin/documents/{document_id}/activate",
        headers=bearer(admin_token),
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["is_active"] is True

    twice = await api_client.post(
        f"/api/v1/admin/documents/{document_id}/activate",
        headers=bearer(admin_token),
    )
    assert twice.status_code == 200
    assert twice.json()["is_active"] is True

    deactivated = await api_client.post(
        f"/api/v1/admin/documents/{document_id}/deactivate",
        headers=bearer(admin_token),
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["is_active"] is False


async def test_activation_requires_ready_status(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    document = await _seed_ready_document(
        migrated_db_session,
        document_storage,
        ingestion_status=IngestionStatus.PENDING,
    )

    response = await api_client.post(
        f"/api/v1/admin/documents/{document.id}/activate",
        headers=bearer(admin_token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_not_ready"


async def test_activation_requires_stored_chunks(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    document = await _seed_ready_document(
        migrated_db_session,
        document_storage,
        with_chunks=False,
    )

    response = await api_client.post(
        f"/api/v1/admin/documents/{document.id}/activate",
        headers=bearer(admin_token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_not_ready"


async def test_activation_requires_complete_storage_metadata(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    document = await _seed_ready_document(
        migrated_db_session,
        document_storage,
        storage_metadata=False,
    )

    response = await api_client.post(
        f"/api/v1/admin/documents/{document.id}/activate",
        headers=bearer(admin_token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_not_ready"


async def test_activation_requires_existing_stored_file(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    document = await _seed_ready_document(
        migrated_db_session,
        document_storage,
        store_file=False,
    )

    response = await api_client.post(
        f"/api/v1/admin/documents/{document.id}/activate",
        headers=bearer(admin_token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_not_ready"


async def test_activation_rejects_modified_stored_file(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    document = await _seed_ready_document(migrated_db_session, document_storage)
    assert document.storage_key is not None

    document_storage.save(
        document.storage_key,
        build_pdf(["Different content after upload"]),
        overwrite=True,
    )

    response = await api_client.post(
        f"/api/v1/admin/documents/{document.id}/activate",
        headers=bearer(admin_token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_integrity_failed"

    await migrated_db_session.refresh(document)
    assert document.is_active is False


async def test_activation_rejects_truncated_stored_file(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    document = await _seed_ready_document(migrated_db_session, document_storage)
    assert document.storage_key is not None

    path = document_storage.root / document.storage_key
    path.write_bytes(path.read_bytes()[:10])

    response = await api_client.post(
        f"/api/v1/admin/documents/{document.id}/activate",
        headers=bearer(admin_token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_integrity_failed"

    await migrated_db_session.refresh(document)
    assert document.is_active is False


async def test_legacy_document_without_storage_cannot_activate(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    document = Document(
        **METADATA,
        file_path="documents/acme/legacy.pdf",
        ingestion_status=IngestionStatus.PENDING,
        is_active=False,
    )
    migrated_db_session.add(document)
    await migrated_db_session.commit()

    response = await api_client.post(
        f"/api/v1/admin/documents/{document.id}/activate",
        headers=bearer(admin_token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_not_ready"


async def test_inactive_uploads_are_not_listed_as_active(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    uploaded = await _upload(api_client, admin_token)
    assert uploaded.status_code == 202

    response = await api_client.get(
        "/api/v1/admin/documents",
        headers=bearer(admin_token),
        params={"is_active": True},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []
