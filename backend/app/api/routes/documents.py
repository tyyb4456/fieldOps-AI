from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_admin_user
from app.api.serializers import (
    document_chunk_response,
    document_response,
)
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.document import (
    DocumentChunkListResponse,
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdate,
)
from app.services import documents as document_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Documents"])


def _document_conflict_error() -> AppError:
    return AppError(
        "Document conflicts with an existing record.",
        status_code=status.HTTP_409_CONFLICT,
        code="document_conflict",
    )


def _document_in_use_error() -> AppError:
    return AppError(
        "Document cannot be deleted in its current state.",
        status_code=status.HTTP_409_CONFLICT,
        code="document_in_use",
    )


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="Admin: list document metadata",
)
async def list_documents(
    manufacturer: str | None = Query(default=None, max_length=150),
    model: str | None = Query(default=None, max_length=150),
    equipment_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentListResponse:
    items, total = await document_service.list_documents(
        session,
        manufacturer=manufacturer,
        model=model,
        equipment_id=equipment_id,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return DocumentListResponse(
        items=[document_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: register inactive document metadata",
)
async def create_document(
    payload: DocumentCreate,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    try:
        document = await document_service.create_document(
            session,
            data=payload,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _document_conflict_error() from exc

    await session.refresh(document)
    logger.info(
        "Document registered",
        extra={
            "event": "document_created",
            "actor_id": str(admin.id),
            "document_id": str(document.id),
            "manufacturer": document.manufacturer,
            "model": document.model,
            "is_active": document.is_active,
        },
    )
    return document_response(document)


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Admin: read document metadata",
)
async def read_document(
    document_id: uuid.UUID,
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    document = await document_service.get_document(session, document_id)
    return document_response(document)


@router.patch(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Admin: update document metadata or activation state",
)
async def update_document(
    document_id: uuid.UUID,
    payload: DocumentUpdate,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    document = await document_service.get_document(
        session,
        document_id,
        for_update=True,
    )
    try:
        updated = await document_service.update_document(
            session,
            document,
            payload,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _document_conflict_error() from exc

    await session.refresh(updated)
    logger.info(
        "Document updated",
        extra={
            "event": "document_updated",
            "actor_id": str(admin.id),
            "document_id": str(updated.id),
            "is_active": updated.is_active,
        },
    )
    return document_response(updated)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Admin: delete document metadata and its chunks",
)
async def delete_document(
    document_id: uuid.UUID,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    document = await document_service.get_document(
        session,
        document_id,
        for_update=True,
    )
    try:
        await document_service.delete_document(session, document)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _document_in_use_error() from exc

    logger.info(
        "Document deleted",
        extra={
            "event": "document_deleted",
            "actor_id": str(admin.id),
            "document_id": str(document_id),
        },
    )


@router.get(
    "/documents/{document_id}/chunks",
    response_model=DocumentChunkListResponse,
    summary="Admin: list a document's stored chunks",
)
async def list_document_chunks(
    document_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentChunkListResponse:
    await document_service.get_document(session, document_id)
    items, total = await document_service.list_document_chunks(
        session,
        document_id,
        limit=limit,
        offset=offset,
    )
    return DocumentChunkListResponse(
        items=[document_chunk_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
