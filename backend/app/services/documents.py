from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.equipment import Equipment
from app.schemas.document import DocumentCreate, DocumentUpdate
from app.services.authorization import AccessDeniedError


async def list_documents(
    session: AsyncSession,
    *,
    manufacturer: str | None,
    model: str | None,
    equipment_id: uuid.UUID | None,
    is_active: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[Document], int]:
    filters = []
    if manufacturer is not None:
        filters.append(Document.manufacturer == manufacturer)
    if model is not None:
        filters.append(Document.model == model)
    if equipment_id is not None:
        equipment = await session.get(Equipment, equipment_id)
        if equipment is None:
            raise AccessDeniedError("Equipment not found")
        filters.append(Document.manufacturer == equipment.manufacturer)
        filters.append(Document.model == equipment.model)
    if is_active is not None:
        filters.append(Document.is_active.is_(is_active))

    total = await session.scalar(
        select(func.count()).select_from(Document).where(*filters)
    )
    statement = (
        select(Document)
        .where(*filters)
        .order_by(Document.created_at.desc(), Document.id.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(statement)
    return list(result.scalars().all()), int(total or 0)


async def get_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Document:
    statement = select(Document).where(Document.id == document_id)
    if for_update:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    result = await session.execute(statement)
    document = result.scalar_one_or_none()
    if document is None:
        raise AccessDeniedError("Document not found")
    return document


async def create_document(
    session: AsyncSession,
    *,
    data: DocumentCreate,
) -> Document:
    document = Document(
        manufacturer=data.manufacturer,
        model=data.model,
        document_name=data.document_name,
        version=data.version,
        file_path=data.file_path,
        is_active=False,
    )
    session.add(document)
    await session.flush()
    return document


async def update_document(
    session: AsyncSession,
    document: Document,
    data: DocumentUpdate,
) -> Document:
    for field in data.model_fields_set:
        setattr(document, field, getattr(data, field))
    await session.flush()
    return document


async def delete_document(
    session: AsyncSession,
    document: Document,
) -> None:
    await session.delete(document)
    await session.flush()


async def list_document_chunks(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> tuple[list[DocumentChunk], int]:
    total = await session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
    )
    result = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(
            DocumentChunk.chunk_index.asc(),
            DocumentChunk.id.asc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)
