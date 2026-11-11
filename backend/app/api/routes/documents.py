from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from langchain_core.documents import Document as LangChainDocument
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.dependencies.auth import require_admin_user
from app.api.dependencies.storage import get_document_storage
from app.api.dependencies.vector_index import get_vector_index
from app.api.serializers import (
    document_chunk_response,
    document_response,
)
from app.core.config import settings
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.document import (
    DocumentChunkListResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdate,
)
from app.services import documents as document_service
from app.services.document_ingestion import (
    DocumentIngestionError,
    DocumentIntegrityError,
    DocumentNotReadyError,
    IngestionInProgressError,
    PdfValidationError,
    activate_document,
    deactivate_document,
    ingest_document,
    load_stored_pdf_documents,
    validate_upload,
)
from app.services.storage import (
    DocumentStorage,
    StorageError,
    StorageFileTooLargeError,
    StorageObjectExistsError,
)
from app.services.storage_coordination import (
    STORAGE_OPERATION_LOCK_KEY,
    advisory_lock,
)
from app.services.vector_index import VectorIndex

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


def _clean_required(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise AppError(
            f"{field_name} must not be blank.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="invalid_document",
        )
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _validation_error(exc: PdfValidationError) -> AppError:
    status_code = (
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        if exc.code == "document_too_large"
        else status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    return AppError(
        exc.message,
        status_code=status_code,
        code=exc.code,
    )


async def _remove_stored_file(
    storage: DocumentStorage,
    storage_key: str,
    *,
    document_id: uuid.UUID | None = None,
) -> None:
    try:
        await run_in_threadpool(storage.delete, storage_key)
    except StorageError:
        logger.warning(
            "Document storage cleanup failed",
            extra={
                "event": "document_storage_cleanup_failed",
                "document_id": (str(document_id) if document_id is not None else None),
            },
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
    summary="Admin: upload a PDF document and ingest it",
)
async def upload_document(
    file: Annotated[UploadFile, File()],
    manufacturer: Annotated[str, Form(min_length=1, max_length=150)],
    model: Annotated[str, Form(min_length=1, max_length=150)],
    document_name: Annotated[str, Form(min_length=1, max_length=255)],
    version: Annotated[str | None, Form(max_length=100)] = None,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
    storage: DocumentStorage = Depends(get_document_storage),
    vector_index: VectorIndex = Depends(get_vector_index),
) -> DocumentResponse:
    manufacturer = _clean_required(manufacturer, "manufacturer")
    model = _clean_required(model, "model")
    document_name = _clean_required(document_name, "document_name")
    version = _clean_optional(version)
    actor_id = admin.id

    max_bytes = settings.max_upload_size_bytes
    try:
        data = await file.read(max_bytes + 1)
    finally:
        await file.close()

    try:
        uploaded = await run_in_threadpool(
            validate_upload,
            filename=file.filename,
            declared_content_type=file.content_type,
            data=data,
            max_bytes=max_bytes,
            allowed_content_types=(settings.allowed_document_content_types_list),
        )
    except PdfValidationError as exc:
        raise _validation_error(exc) from exc

    storage_key = ""
    page_documents: list[LangChainDocument] = []
    async with advisory_lock(session, STORAGE_OPERATION_LOCK_KEY):
        for _attempt in range(3):
            candidate = storage.generate_key(uploaded.original_filename)
            try:
                await run_in_threadpool(
                    storage.save,
                    candidate,
                    uploaded.data,
                )
            except StorageObjectExistsError:
                continue
            except StorageFileTooLargeError as exc:
                raise AppError(
                    "The uploaded file exceeds the maximum allowed size.",
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    code="document_too_large",
                ) from exc
            except StorageError as exc:
                logger.warning(
                    "Document storage write failed",
                    extra={"event": "document_storage_write_failed"},
                )
                raise AppError(
                    "Document storage is unavailable.",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    code="document_storage_unavailable",
                ) from exc
            storage_key = candidate
            break

        if not storage_key:
            raise AppError(
                "Document storage could not allocate a unique key.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="document_storage_unavailable",
            )

        try:
            page_documents = await run_in_threadpool(
                load_stored_pdf_documents,
                storage,
                storage_key,
                max_pages=settings.max_pdf_pages,
            )
        except PdfValidationError as exc:
            await _remove_stored_file(storage, storage_key)
            raise _validation_error(exc) from exc
        except DocumentIngestionError as exc:
            await _remove_stored_file(storage, storage_key)
            logger.warning(
                "Document storage read failed during upload validation",
                extra={"event": "document_storage_read_failed"},
            )
            raise AppError(
                "Document storage is unavailable.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="document_storage_unavailable",
            ) from exc

        try:
            document = await document_service.create_uploaded_document(
                session,
                uploaded=uploaded,
                storage_key=storage_key,
                manufacturer=manufacturer,
                model=model,
                document_name=document_name,
                version=version,
                uploaded_by_id=actor_id,
            )
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            await _remove_stored_file(storage, storage_key)
            raise _document_conflict_error() from exc
        except Exception:
            await session.rollback()
            await _remove_stored_file(storage, storage_key)
            raise

    document = await ingest_document(
        session,
        document.id,
        storage,
        vector_index,
        max_pages=settings.max_pdf_pages,
        chunk_size=settings.document_chunk_size,
        chunk_overlap=settings.document_chunk_overlap,
        ingestion_version=settings.document_ingestion_version,
        prepared_documents=page_documents,
    )

    logger.info(
        "Document uploaded",
        extra={
            "event": "document_created",
            "actor_id": str(actor_id),
            "document_id": str(document.id),
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
    summary="Admin: update document metadata",
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
        },
    )
    return document_response(updated)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Admin: delete document metadata, chunks and stored file",
)
async def delete_document(
    document_id: uuid.UUID,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
    storage: DocumentStorage = Depends(get_document_storage),
) -> None:
    document = await document_service.get_document(
        session,
        document_id,
        for_update=True,
    )
    storage_key = document.storage_key
    try:
        await document_service.delete_document(session, document)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _document_in_use_error() from exc

    if storage_key:
        try:
            await run_in_threadpool(storage.delete, storage_key)
        except StorageError:
            logger.warning(
                "Document storage cleanup failed after deletion",
                extra={
                    "event": "document_storage_cleanup_failed",
                    "document_id": str(document_id),
                },
            )

    logger.info(
        "Document deleted",
        extra={
            "event": "document_deleted",
            "actor_id": str(admin.id),
            "document_id": str(document_id),
        },
    )


@router.post(
    "/documents/{document_id}/ingest",
    response_model=DocumentResponse,
    summary="Admin: re-ingest a stored PDF document",
)
async def ingest_stored_document(
    document_id: uuid.UUID,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
    storage: DocumentStorage = Depends(get_document_storage),
    vector_index: VectorIndex = Depends(get_vector_index),
) -> DocumentResponse:
    actor_id = admin.id
    try:
        document = await ingest_document(
            session,
            document_id,
            storage,
            vector_index,
            max_pages=settings.max_pdf_pages,
            chunk_size=settings.document_chunk_size,
            chunk_overlap=settings.document_chunk_overlap,
            ingestion_version=settings.document_ingestion_version,
        )
    except IngestionInProgressError as exc:
        raise AppError(
            "Document ingestion is already in progress.",
            status_code=status.HTTP_409_CONFLICT,
            code="ingestion_in_progress",
        ) from exc

    logger.info(
        "Document ingestion completed",
        extra={
            "event": "document_ingested",
            "actor_id": str(actor_id),
            "document_id": str(document.id),
        },
    )
    return document_response(document)


@router.post(
    "/documents/{document_id}/activate",
    response_model=DocumentResponse,
    summary="Admin: activate an ingested document",
)
async def activate_stored_document(
    document_id: uuid.UUID,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
    storage: DocumentStorage = Depends(get_document_storage),
) -> DocumentResponse:
    actor_id = admin.id
    try:
        document = await activate_document(
            session,
            document_id,
            storage,
        )
    except DocumentNotReadyError as exc:
        raise AppError(
            str(exc),
            status_code=status.HTTP_409_CONFLICT,
            code="document_not_ready",
        ) from exc
    except DocumentIntegrityError as exc:
        raise AppError(
            str(exc),
            status_code=status.HTTP_409_CONFLICT,
            code="document_integrity_failed",
        ) from exc

    await session.refresh(document)
    logger.info(
        "Document activated",
        extra={
            "event": "document_activated",
            "actor_id": str(actor_id),
            "document_id": str(document.id),
        },
    )
    return document_response(document)


@router.post(
    "/documents/{document_id}/deactivate",
    response_model=DocumentResponse,
    summary="Admin: deactivate a document",
)
async def deactivate_stored_document(
    document_id: uuid.UUID,
    admin: User = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    document = await deactivate_document(session, document_id)
    await session.refresh(document)
    logger.info(
        "Document deactivated",
        extra={
            "event": "document_deactivated",
            "actor_id": str(admin.id),
            "document_id": str(document.id),
        },
    )
    return document_response(document)


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
