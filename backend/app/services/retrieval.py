from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import IngestionStatus
from app.models.user import User
from app.services.authorization import (
    AccessDeniedError,
    is_admin,
    is_technician,
)
from app.services.vector_index import VectorIndex

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    manufacturer: str
    model: str
    version: str | None
    page_number: int | None
    chunk_index: int
    content: str
    distance: float
    similarity: float


async def authorized_document_ids(
    session: AsyncSession,
    *,
    manufacturer: str | None = None,
    model: str | None = None,
) -> list[uuid.UUID]:
    statement = select(Document.id).where(
        Document.is_active.is_(True),
        Document.ingestion_status == IngestionStatus.READY,
    )
    if manufacturer:
        statement = statement.where(
            func.lower(Document.manufacturer) == manufacturer.lower()
        )
    if model:
        statement = statement.where(func.lower(Document.model) == model.lower())

    result = await session.execute(statement)
    return list(result.scalars().all())


async def documents_requiring_reembedding(
    session: AsyncSession,
    *,
    expected_model: str,
) -> list[uuid.UUID]:
    """Return active, ready documents whose indexed model is not expected.

    These documents remain valid but are intentionally excluded from search
    until they are re-ingested with the configured embedding model.
    """

    statement = select(Document.id).where(
        Document.is_active.is_(True),
        Document.ingestion_status == IngestionStatus.READY,
        Document.embedding_model.is_distinct_from(expected_model),
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


async def search_documents(
    session: AsyncSession,
    user: User,
    *,
    vector_index: VectorIndex,
    query: str,
    manufacturer: str | None,
    model: str | None,
    top_k: int,
) -> list[RetrievedChunk]:
    if not (is_admin(user) or is_technician(user)):
        raise AccessDeniedError("Knowledge base access denied")

    normalized_query = query.strip()
    if not normalized_query:
        return []

    permitted_document_ids = await authorized_document_ids(
        session,
        manufacturer=manufacturer.strip() if manufacturer else None,
        model=model.strip() if model else None,
    )
    if not permitted_document_ids:
        return []

    hits = await vector_index.search(
        query=normalized_query,
        document_ids=permitted_document_ids,
        k=top_k,
    )
    if not hits:
        return []

    distances: dict[uuid.UUID, float] = {}
    for hit in hits:
        existing = distances.get(hit.chunk_id)
        if existing is None or hit.distance < existing:
            distances[hit.chunk_id] = hit.distance

    statement = (
        select(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            DocumentChunk.id.in_(list(distances)),
            DocumentChunk.is_current.is_(True),
            Document.id.in_(permitted_document_ids),
            Document.is_active.is_(True),
            Document.ingestion_status == IngestionStatus.READY,
        )
    )
    rows = (await session.execute(statement)).all()

    results: list[RetrievedChunk] = []
    for chunk, document in rows:
        distance = distances.get(chunk.id)
        if distance is None:
            continue
        similarity = max(0.0, min(1.0, 1.0 - distance))
        results.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=document.id,
                document_name=document.document_name,
                manufacturer=document.manufacturer,
                model=document.model,
                version=document.version,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                distance=distance,
                similarity=similarity,
            )
        )

    results.sort(key=lambda item: item.distance)
    logger.info(
        "Knowledge base search completed",
        extra={
            "event": "knowledge_base_search",
            "result_count": len(results),
            "authorized_document_count": len(permitted_document_ids),
        },
    )
    return results
