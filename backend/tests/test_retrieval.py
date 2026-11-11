from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import IngestionStatus
from app.services.vector_index import VectorIndexError, VectorSearchHit
from tests.support import bearer, seed_admin, seed_customer, seed_technician


async def _seed_document(
    session: AsyncSession,
    *,
    manufacturer: str = "Acme Solar",
    model: str = "INV-5000",
    is_active: bool = True,
    ingestion_status: IngestionStatus = IngestionStatus.READY,
    chunks: tuple[str, ...] = ("Error E-05 requires inspection.",),
) -> tuple[Document, list[DocumentChunk]]:
    document = Document(
        manufacturer=manufacturer,
        model=model,
        document_name=f"Manual {uuid.uuid4().hex}",
        version="1.0",
        ingestion_status=ingestion_status,
        is_active=is_active,
    )
    session.add(document)
    await session.flush()

    stored_chunks = [
        DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            content=content,
            page_number=1,
        )
        for index, content in enumerate(chunks)
    ]
    session.add_all(stored_chunks)
    await session.commit()
    return document, stored_chunks


async def test_search_requires_authentication(api_client: Any) -> None:
    response = await api_client.post(
        "/api/v1/knowledge/search",
        json={"query": "error code"},
    )

    assert response.status_code == 401


async def test_search_rejects_customers(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, customer_token = await seed_customer(migrated_db_session)

    response = await api_client.post(
        "/api/v1/knowledge/search",
        headers=bearer(customer_token),
        json={"query": "error code"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_search_restricts_retrieval_to_authorized_active_documents(
    api_client: Any,
    migrated_db_session: AsyncSession,
    vector_index: Any,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    allowed, allowed_chunks = await _seed_document(migrated_db_session)
    inactive, inactive_chunks = await _seed_document(
        migrated_db_session,
        is_active=False,
    )
    processing, processing_chunks = await _seed_document(
        migrated_db_session,
        is_active=False,
        ingestion_status=IngestionStatus.PROCESSING,
    )
    other_manufacturer, other_chunks = await _seed_document(
        migrated_db_session,
        manufacturer="Other Solar",
    )

    vector_index.search_hits = [
        VectorSearchHit(chunk_id=inactive_chunks[0].id, distance=0.01),
        VectorSearchHit(chunk_id=processing_chunks[0].id, distance=0.02),
        VectorSearchHit(chunk_id=other_chunks[0].id, distance=0.03),
        VectorSearchHit(chunk_id=allowed_chunks[0].id, distance=0.4),
    ]

    response = await api_client.post(
        "/api/v1/knowledge/search",
        headers=bearer(admin_token),
        json={
            "query": "  error code  ",
            "manufacturer": "  acme solar ",
            "model": " inv-5000 ",
            "top_k": 5,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["top_k"] == 5
    assert [item["chunk_id"] for item in body["items"]] == [
        str(allowed_chunks[0].id)
    ]
    assert body["items"][0]["document_id"] == str(allowed.id)
    assert body["items"][0]["content"] == "Error E-05 requires inspection."
    assert body["items"][0]["distance"] == 0.4
    assert body["items"][0]["similarity"] == 0.6

    assert vector_index.search_calls == [("error code", [allowed.id], 5)]
    assert inactive.id not in vector_index.search_calls[0][1]
    assert processing.id not in vector_index.search_calls[0][1]
    assert other_manufacturer.id not in vector_index.search_calls[0][1]


async def test_search_does_not_call_vector_store_without_authorized_documents(
    api_client: Any,
    migrated_db_session: AsyncSession,
    vector_index: Any,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    await _seed_document(
        migrated_db_session,
        is_active=False,
        ingestion_status=IngestionStatus.FAILED,
    )

    response = await api_client.post(
        "/api/v1/knowledge/search",
        headers=bearer(admin_token),
        json={"query": "error code"},
    )

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert vector_index.search_calls == []


async def test_search_allows_technicians(
    api_client: Any,
    migrated_db_session: AsyncSession,
    vector_index: Any,
) -> None:
    _, _, technician_token = await seed_technician(migrated_db_session)
    document, chunks = await _seed_document(migrated_db_session)
    vector_index.search_hits = [
        VectorSearchHit(chunk_id=chunks[0].id, distance=1.6)
    ]

    response = await api_client.post(
        "/api/v1/knowledge/search",
        headers=bearer(technician_token),
        json={"query": "error code"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["document_id"] == str(document.id)
    assert response.json()["items"][0]["similarity"] == 0.0


async def test_search_returns_unavailable_when_vector_store_fails(
    api_client: Any,
    migrated_db_session: AsyncSession,
    vector_index: Any,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    await _seed_document(migrated_db_session)
    vector_index.search_error = VectorIndexError("store down")

    response = await api_client.post(
        "/api/v1/knowledge/search",
        headers=bearer(admin_token),
        json={"query": "error code"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "retrieval_unavailable"


async def test_search_validates_query_and_top_k(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)

    blank = await api_client.post(
        "/api/v1/knowledge/search",
        headers=bearer(admin_token),
        json={"query": "   "},
    )
    too_many = await api_client.post(
        "/api/v1/knowledge/search",
        headers=bearer(admin_token),
        json={"query": "error code", "top_k": 1000},
    )

    assert blank.status_code == 422
    assert too_many.status_code == 422
