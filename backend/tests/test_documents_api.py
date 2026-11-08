from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from tests.support import (
    bearer,
    seed_admin,
    seed_customer,
    seed_equipment,
    seed_technician,
)

DOCUMENT_PAYLOAD = {
    "manufacturer": "Acme Solar",
    "model": "INV-5000",
    "document_name": "INV-5000 Technical Manual",
    "version": "1.0",
    "file_path": "documents/acme/inv-5000-v1.pdf",
}


async def _seed_admin_token(session: AsyncSession) -> tuple[Any, str]:
    return await seed_admin(session)


async def _create_document(
    api_client: Any,
    admin_token: str,
    **overrides: object,
) -> Any:
    payload = {**DOCUMENT_PAYLOAD, **overrides}
    return await api_client.post(
        "/api/v1/admin/documents",
        headers=bearer(admin_token),
        json=payload,
    )


async def _seed_document(
    session: AsyncSession,
    **overrides: object,
) -> Document:
    values: dict[str, object] = {**DOCUMENT_PAYLOAD, **overrides}
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


async def test_admin_registers_inactive_document_metadata(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await _seed_admin_token(migrated_db_session)

    response = await _create_document(
        api_client,
        admin_token,
        manufacturer="  Acme Solar  ",
        document_name="  INV-5000 Technical Manual  ",
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["manufacturer"] == "Acme Solar"
    assert body["document_name"] == "INV-5000 Technical Manual"
    assert body["is_active"] is False


async def test_document_duplicate_returns_conflict(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await _seed_admin_token(migrated_db_session)
    first = await _create_document(api_client, admin_token)
    assert first.status_code == 201, first.text

    duplicate = await _create_document(api_client, admin_token)

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "document_conflict"


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


async def test_admin_reads_and_activates_document(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await _seed_admin_token(migrated_db_session)
    document = await _seed_document(migrated_db_session)

    read = await api_client.get(
        f"/api/v1/admin/documents/{document.id}",
        headers=bearer(admin_token),
    )
    assert read.status_code == 200
    assert read.json()["id"] == str(document.id)

    updated = await api_client.patch(
        f"/api/v1/admin/documents/{document.id}",
        headers=bearer(admin_token),
        json={
            "is_active": True,
            "version": "  2.0  ",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["is_active"] is True
    assert updated.json()["version"] == "2.0"

    empty = await api_client.patch(
        f"/api/v1/admin/documents/{document.id}",
        headers=bearer(admin_token),
        json={},
    )
    assert empty.status_code == 422

    null_name = await api_client.patch(
        f"/api/v1/admin/documents/{document.id}",
        headers=bearer(admin_token),
        json={"document_name": None},
    )
    assert null_name.status_code == 422

    null_active = await api_client.patch(
        f"/api/v1/admin/documents/{document.id}",
        headers=bearer(admin_token),
        json={"is_active": None},
    )
    assert null_active.status_code == 422

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


async def test_admin_delete_removes_document_and_chunks(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await _seed_admin_token(migrated_db_session)
    document = await _seed_document(migrated_db_session)
    migrated_db_session.add(
        DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            content="Chunk to be cascaded",
        )
    )
    await migrated_db_session.commit()

    deleted = await api_client.delete(
        f"/api/v1/admin/documents/{document.id}",
        headers=bearer(admin_token),
    )

    assert deleted.status_code == 204

    read_after = await api_client.get(
        f"/api/v1/admin/documents/{document.id}",
        headers=bearer(admin_token),
    )
    assert read_after.status_code == 404

    chunk_count = await migrated_db_session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
    )
    assert chunk_count == 0
