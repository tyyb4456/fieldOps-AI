from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import IngestionStatus
from app.services.storage import LocalFileStorage
from tests.pdf_factory import build_pdf
from tests.support import (
    bearer,
    seed_admin,
    seed_customer,
    seed_equipment,
    seed_technician,
)

DOCUMENT_METADATA = {
    "manufacturer": "Acme Solar",
    "model": "INV-5000",
    "document_name": "INV-5000 Technical Manual",
    "version": "1.0",
}

DOCUMENT_PAYLOAD = {
    **DOCUMENT_METADATA,
    "file_path": "documents/acme/inv-5000-v1.pdf",
}


async def _seed_admin_token(session: AsyncSession) -> tuple[Any, str]:
    return await seed_admin(session)


async def _upload_document(
    api_client: Any,
    admin_token: str,
    *,
    page_texts: list[str] | None = None,
    filename: str = "inv-5000.pdf",
    content_type: str = "application/pdf",
    **overrides: object,
) -> Any:
    metadata = {**DOCUMENT_METADATA, **overrides}
    data = build_pdf(page_texts or ["Error E-05 requires inspection."])
    return await api_client.post(
        "/api/v1/admin/documents",
        headers=bearer(admin_token),
        data=metadata,
        files={"file": (filename, data, content_type)},
    )


async def _seed_document(
    session: AsyncSession,
    **overrides: object,
) -> Document:
    values: dict[str, object] = {**DOCUMENT_PAYLOAD}
    values.update(overrides)
    document = Document(**values)
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


async def test_document_endpoints_require_authentication(
    api_client: Any,
) -> None:
    response = await api_client.get("/api/v1/admin/documents")

    assert response.status_code == 401


async def test_document_endpoints_are_admin_only(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, customer_token = await seed_customer(migrated_db_session)
    _, _, technician_token = await seed_technician(migrated_db_session)

    for token in (customer_token, technician_token):
        response = await api_client.get(
            "/api/v1/admin/documents",
            headers=bearer(token),
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"


async def test_admin_uploads_inactive_ingested_document(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    admin, admin_token = await _seed_admin_token(migrated_db_session)

    response = await _upload_document(
        api_client,
        admin_token,
        manufacturer="  Acme Solar  ",
        document_name="  INV-5000 Technical Manual  ",
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["manufacturer"] == "Acme Solar"
    assert body["document_name"] == "INV-5000 Technical Manual"
    assert body["original_filename"] == "inv-5000.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["byte_size"] > 0
    assert len(body["checksum_sha256"]) == 64
    assert body["uploaded_by_id"] == str(admin.id)
    assert body["ingestion_status"] == "ready"
    assert body["is_active"] is False
    assert "file_path" not in body
    assert "storage_key" not in body

    chunks = await migrated_db_session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == body["id"])
        .order_by(DocumentChunk.chunk_index)
    )
    stored_chunks = list(chunks.scalars())
    assert len(stored_chunks) == 1
    assert stored_chunks[0].page_number == 1
    assert stored_chunks[0].chunk_metadata["ingestion_version"] == "1"

    stored_keys = list(document_storage.iter_keys())
    assert len(stored_keys) == 1


async def test_document_duplicate_returns_conflict_and_cleans_storage(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await _seed_admin_token(migrated_db_session)
    first = await _upload_document(api_client, admin_token)
    assert first.status_code == 201, first.text

    duplicate = await _upload_document(api_client, admin_token)

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "document_conflict"
    assert len(list(document_storage.iter_keys())) == 1


async def test_document_list_filters_by_equipment_and_state(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    _, admin_token = await _seed_admin_token(migrated_db_session)

    active = await _seed_document(
        migrated_db_session,
        document_name="Active Manual",
        file_path="documents/acme/active.pdf",
        ingestion_status=IngestionStatus.READY,
        is_active=True,
    )
    await _seed_document(
        migrated_db_session,
        document_name="Inactive Manual",
        file_path="documents/acme/inactive.pdf",
        is_active=False,
    )
    await _seed_document(
        migrated_db_session,
        manufacturer="Other Vendor",
        model="X-100",
        document_name="Other Manual",
        file_path="documents/other/manual.pdf",
        ingestion_status=IngestionStatus.READY,
        is_active=True,
    )

    equipment_list = await api_client.get(
        "/api/v1/admin/documents",
        headers=bearer(admin_token),
        params={"equipment_id": str(equipment.id), "is_active": True},
    )

    assert equipment_list.status_code == 200, equipment_list.text
    body = equipment_list.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(active.id)

    missing_equipment = await api_client.get(
        "/api/v1/admin/documents",
        headers=bearer(admin_token),
        params={
            "equipment_id": "00000000-0000-0000-0000-000000000000"
        },
    )
    assert missing_equipment.status_code == 404

    inactive = await api_client.get(
        "/api/v1/admin/documents",
        headers=bearer(admin_token),
        params={"is_active": False},
    )
    assert inactive.status_code == 200
    assert inactive.json()["total"] == 1
    assert inactive.json()["items"][0]["document_name"] == "Inactive Manual"

    by_manufacturer = await api_client.get(
        "/api/v1/admin/documents",
        headers=bearer(admin_token),
        params={"manufacturer": "Other Vendor", "model": "X-100"},
    )
    assert by_manufacturer.status_code == 200
    assert by_manufacturer.json()["total"] == 1
    assert by_manufacturer.json()["items"][0]["document_name"] == (
        "Other Manual"
    )

    paged = await api_client.get(
        "/api/v1/admin/documents",
        headers=bearer(admin_token),
        params={"limit": 1, "offset": 1},
    )
    assert paged.status_code == 200
    assert paged.json()["total"] == 3
    assert len(paged.json()["items"]) == 1


async def test_admin_reads_and_updates_metadata_without_activation(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await _seed_admin_token(migrated_db_session)
    uploaded = await _upload_document(api_client, admin_token)
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]

    read = await api_client.get(
        f"/api/v1/admin/documents/{document_id}",
        headers=bearer(admin_token),
    )
    assert read.status_code == 200
    assert read.json()["id"] == document_id

    updated = await api_client.patch(
        f"/api/v1/admin/documents/{document_id}",
        headers=bearer(admin_token),
        json={"version": "  2.0  "},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == "2.0"
    assert updated.json()["is_active"] is False

    empty = await api_client.patch(
        f"/api/v1/admin/documents/{document_id}",
        headers=bearer(admin_token),
        json={},
    )
    assert empty.status_code == 422

    null_name = await api_client.patch(
        f"/api/v1/admin/documents/{document_id}",
        headers=bearer(admin_token),
        json={"document_name": None},
    )
    assert null_name.status_code == 422

    for field, value in (
        ("is_active", True),
        ("file_path", "public/evil.pdf"),
        ("storage_key", "aa/evil.pdf"),
        ("checksum_sha256", "b" * 64),
        ("ingestion_status", "ready"),
        ("uploaded_by_id", str(uuid.uuid4())),
    ):
        response = await api_client.patch(
            f"/api/v1/admin/documents/{document_id}",
            headers=bearer(admin_token),
            json={field: value},
        )
        assert response.status_code == 422, field

    missing = await api_client.get(
        "/api/v1/admin/documents/00000000-0000-0000-0000-000000000000",
        headers=bearer(admin_token),
    )
    assert missing.status_code == 404


async def test_document_chunks_are_listed_in_order(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await _seed_admin_token(migrated_db_session)
    document = await _seed_document(migrated_db_session)
    migrated_db_session.add_all(
        [
            DocumentChunk(
                document_id=document.id,
                chunk_index=2,
                content="Third section",
                page_number=44,
                chunk_metadata={"section": "maintenance"},
            ),
            DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content="First section",
                page_number=42,
                chunk_metadata={"section": "safety"},
            ),
        ]
    )
    await migrated_db_session.commit()

    response = await api_client.get(
        f"/api/v1/admin/documents/{document.id}/chunks",
        headers=bearer(admin_token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert [item["chunk_index"] for item in body["items"]] == [0, 2]
    assert body["items"][0]["content"] == "First section"
    assert body["items"][0]["metadata"] == {"section": "safety"}

    missing_document = await api_client.get(
        "/api/v1/admin/documents/"
        "00000000-0000-0000-0000-000000000000/chunks",
        headers=bearer(admin_token),
    )
    assert missing_document.status_code == 404


async def test_admin_delete_removes_document_chunks_and_stored_file(
    api_client: Any,
    migrated_db_session: AsyncSession,
    document_storage: LocalFileStorage,
) -> None:
    _, admin_token = await _seed_admin_token(migrated_db_session)
    uploaded = await _upload_document(api_client, admin_token)
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]
    assert len(list(document_storage.iter_keys())) == 1

    deleted = await api_client.delete(
        f"/api/v1/admin/documents/{document_id}",
        headers=bearer(admin_token),
    )

    assert deleted.status_code == 204

    read_after = await api_client.get(
        f"/api/v1/admin/documents/{document_id}",
        headers=bearer(admin_token),
    )
    assert read_after.status_code == 404

    chunk_count = await migrated_db_session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
    )
    assert chunk_count == 0
    assert list(document_storage.iter_keys()) == []
