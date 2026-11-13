from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document as LangChainDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf.errors import FileNotDecryptedError
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import IngestionStatus
from app.services.documents.storage import DocumentStorage, StorageError
from app.services.documents.storage_coordination import (
    advisory_lock,
    document_ingestion_lock_key,
)
from app.services.rag.vector_index import VectorIndex
from app.services.shared.authorization import AccessDeniedError
from app.services.shared.retry import TransientError, is_transient_error

logger = logging.getLogger(__name__)

PDF_CONTENT_TYPE = "application/pdf"
PDF_EXTENSION = ".pdf"

INGESTION_ERROR_PARSE = "The PDF could not be read."
INGESTION_ERROR_EMPTY = "The PDF contains no extractable text."
INGESTION_ERROR_PAGES = "The PDF exceeds the maximum allowed page count."
INGESTION_ERROR_STORAGE = "The stored document file is missing or unreadable."
INGESTION_ERROR_INTEGRITY = (
    "The stored document does not match its recorded integrity metadata."
)
INGESTION_ERROR_UNEXPECTED = "The document could not be processed."
INGESTION_ERROR_EMBEDDING = (
    "The document could not be embedded for retrieval."
)
INGESTION_ERROR_RECOVERED = (
    "The previous ingestion was interrupted. Re-ingest the document."
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_ONLY = re.compile(r"^\s*$")
_EXCESS_NEWLINES = re.compile(r"\n{3,}")
_HASH_CHUNK_SIZE = 1024 * 1024


class PdfValidationError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_document",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class DocumentIngestionError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DocumentIntegrityError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class TransientIngestionError(DocumentIngestionError, TransientError):
    """Retryable ingestion failure; the document is left FAILED for a retry."""


class IngestionInProgressError(Exception):
    pass


class DocumentNotReadyError(Exception):
    pass


class DocumentRecoveryError(Exception):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class UploadedPdf:
    data: bytes
    original_filename: str
    content_type: str
    checksum_sha256: str


@dataclass(frozen=True)
class ChunkDraft:
    chunk_index: int
    content: str
    page_number: int
    char_start: int
    char_end: int


def is_valid_sha256(value: str | None) -> bool:
    if value is None:
        return False
    return bool(value) and _SHA256_PATTERN.fullmatch(value) is not None


def sanitize_original_filename(filename: str) -> str:
    normalized = filename.replace("\\", "/").strip()
    basename = PurePosixPath(normalized).name
    basename = _CONTROL_CHARACTERS.sub("", basename).strip()
    if basename in {"", ".", ".."}:
        raise PdfValidationError("A PDF filename is required.")
    if len(basename) > 255:
        raise PdfValidationError("The PDF filename is too long.")
    return basename


def normalize_extracted_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _CONTROL_CHARACTERS.sub("", normalized)
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    normalized = _EXCESS_NEWLINES.sub("\n\n", normalized)
    return normalized.strip()


def validate_upload(
    *,
    filename: str | None,
    declared_content_type: str | None,
    data: bytes,
    max_bytes: int,
    allowed_content_types: list[str],
) -> UploadedPdf:
    if not filename:
        raise PdfValidationError("A PDF file is required.")
    original_filename = sanitize_original_filename(filename)
    if PurePosixPath(original_filename).suffix.lower() != PDF_EXTENSION:
        raise PdfValidationError("Only PDF documents are supported.")

    content_type = (declared_content_type or "").split(";", 1)[0]
    content_type = content_type.strip().lower()
    if content_type not in allowed_content_types:
        raise PdfValidationError("The declared content type is not supported.")

    if not data:
        raise PdfValidationError("The uploaded file is empty.")
    if len(data) > max_bytes:
        raise PdfValidationError(
            "The uploaded file exceeds the maximum allowed size.",
            code="document_too_large",
        )
    if b"%PDF-" not in data[:1024]:
        raise PdfValidationError(
            "The uploaded file does not have a valid PDF signature."
        )

    return UploadedPdf(
        data=data,
        original_filename=original_filename,
        content_type=content_type,
        checksum_sha256=hashlib.sha256(data).hexdigest(),
    )


def load_pdf_documents(
    path: str | Path,
    *,
    max_pages: int,
) -> list[LangChainDocument]:
    """Load a PDF page by page using LangChain's PyPDFLoader.

    ``PyPDFLoader`` reports zero-based page numbers through ``metadata["page"]``
    and keeps every page as a separate Document. Empty pages are returned with
    empty content and are filtered later, during normalization.
    """

    try:
        loader = PyPDFLoader(file_path=str(path), mode="page")
        documents = loader.load()
    except FileNotDecryptedError as exc:
        raise PdfValidationError(
            "Encrypted PDF files are not supported."
        ) from exc
    except Exception as exc:
        raise PdfValidationError("The uploaded file is not a valid PDF.") from exc

    if not documents:
        raise PdfValidationError("The PDF does not contain any pages.")
    if len(documents) > max_pages:
        raise PdfValidationError(
            "The PDF exceeds the maximum allowed page count.",
            code="document_page_limit",
        )
    return documents


def load_stored_pdf_documents(
    storage: DocumentStorage,
    key: str,
    *,
    max_pages: int,
) -> list[LangChainDocument]:
    try:
        path = storage.local_path(key)
    except StorageError as exc:
        raise DocumentIngestionError(INGESTION_ERROR_STORAGE) from exc
    return load_pdf_documents(path, max_pages=max_pages)


def _resolve_char_start(
    page_text: str,
    content: str,
    start_index: object,
    *,
    search_from: int,
) -> int:
    if (
        isinstance(start_index, int)
        and start_index >= 0
        and page_text.startswith(content, start_index)
    ):
        return start_index

    resolved = page_text.find(content, max(0, search_from))
    if resolved < 0:
        resolved = page_text.find(content)
    if resolved < 0:
        raise DocumentIngestionError(INGESTION_ERROR_PARSE)
    return resolved


def split_page_documents(
    page_documents: Sequence[LangChainDocument],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[ChunkDraft]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    normalized_pages: list[LangChainDocument] = []
    page_texts: dict[int, str] = {}
    for document in page_documents:
        page = document.metadata.get("page")
        if not isinstance(page, int):
            raise DocumentIngestionError(INGESTION_ERROR_PARSE)
        text = normalize_extracted_text(document.page_content)
        if _WHITESPACE_ONLY.match(text):
            continue
        page_texts[page] = text
        normalized_pages.append(
            LangChainDocument(page_content=text, metadata={"page": page})
        )

    if not normalized_pages:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        add_start_index=True,
    )
    split_documents = splitter.split_documents(normalized_pages)

    drafts: list[ChunkDraft] = []
    previous_end: dict[int, int] = {}
    for document in split_documents:
        page = document.metadata.get("page")
        if not isinstance(page, int) or page not in page_texts:
            raise DocumentIngestionError(INGESTION_ERROR_PARSE)

        page_text = page_texts[page]
        content = document.page_content
        if not content.strip():
            continue

        char_start = _resolve_char_start(
            page_text,
            content,
            document.metadata.get("start_index"),
            search_from=previous_end.get(page, 0) - chunk_overlap,
        )
        char_end = char_start + len(content)
        previous_end[page] = char_end
        drafts.append(
            ChunkDraft(
                chunk_index=len(drafts),
                content=content,
                page_number=page + 1,
                char_start=char_start,
                char_end=char_end,
            )
        )
    return drafts


def measure_stored_object(
    storage: DocumentStorage,
    key: str,
) -> tuple[int, str]:
    hasher = hashlib.sha256()
    size = 0
    try:
        with storage.open(key) as handle:
            while True:
                chunk = handle.read(_HASH_CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                hasher.update(chunk)
    except StorageError as exc:
        raise DocumentIngestionError(INGESTION_ERROR_STORAGE) from exc
    return size, hasher.hexdigest()


def _verify_stored_metadata(
    document: Document,
    *,
    size: int,
    checksum: str,
) -> None:
    if not is_valid_sha256(document.checksum_sha256):
        raise DocumentIngestionError(INGESTION_ERROR_INTEGRITY)
    if document.byte_size is None or document.byte_size < 1:
        raise DocumentIngestionError(INGESTION_ERROR_INTEGRITY)
    if size != document.byte_size:
        raise DocumentIngestionError(INGESTION_ERROR_INTEGRITY)
    if checksum != document.checksum_sha256:
        raise DocumentIngestionError(INGESTION_ERROR_INTEGRITY)


def _chunk_metadata(
    chunk: ChunkDraft,
    *,
    ingestion_version: str,
) -> dict[str, object]:
    return {
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "ingestion_version": ingestion_version,
    }


async def _lock_document(
    session: AsyncSession,
    document_id: uuid.UUID,
) -> Document:
    statement = (
        select(Document)
        .where(Document.id == document_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    document = (await session.execute(statement)).scalar_one_or_none()
    if document is None:
        raise AccessDeniedError("Document not found")
    return document


async def _mark_processing(
    session: AsyncSession,
    document_id: uuid.UUID,
) -> Document:
    document = await _lock_document(session, document_id)
    if document.ingestion_status is IngestionStatus.PROCESSING:
        await session.rollback()
        raise IngestionInProgressError("Document ingestion is already in progress.")

    document.ingestion_status = IngestionStatus.PROCESSING
    document.ingestion_error = None
    document.ingestion_started_at = datetime.now(UTC)
    document.is_active = False
    await session.commit()
    return document


def _build_staged_chunks(
    document_id: uuid.UUID,
    chunks: list[ChunkDraft],
    *,
    ingestion_version: str,
) -> list[DocumentChunk]:
    """Build the replacement chunk set without touching the current set.

    IDs are assigned before persistence so the vector store can write rows for
    the exact chunk identities that will later be promoted.
    """

    return [
        DocumentChunk(
            id=uuid.uuid4(),
            document_id=document_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            page_number=chunk.page_number,
            chunk_metadata=_chunk_metadata(
                chunk,
                ingestion_version=ingestion_version,
            ),
            is_current=False,
        )
        for chunk in chunks
    ]


async def _discard_staged_chunks(
    session: AsyncSession,
    document_id: uuid.UUID,
) -> None:
    """Remove any incomplete replacement chunks and their cascaded vectors."""

    await session.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.is_current.is_(False),
        )
    )


async def _mark_failed(
    session: AsyncSession,
    document_id: uuid.UUID,
    message: str,
) -> Document:
    document = await _lock_document(session, document_id)
    await _discard_staged_chunks(session, document_id)
    document.ingestion_status = IngestionStatus.FAILED
    document.ingestion_error = message
    document.ingestion_started_at = None
    document.is_active = False
    await session.commit()
    return document


async def _fail_ingestion(
    session: AsyncSession,
    document_id: uuid.UUID,
    message: str,
    exc: BaseException,
) -> Document:
    """Record a terminal failure and re-raise transient failures for retry.

    The document is always moved out of PROCESSING so a Celery retry can claim
    it again. Transient failures additionally propagate a typed error so the
    task layer retries instead of treating the failure as final.
    """

    document = await _mark_failed(session, document_id, message)
    if is_transient_error(exc):
        raise TransientIngestionError(message) from exc
    return document


async def _stage_chunks(
    session: AsyncSession,
    document_id: uuid.UUID,
    stored_chunks: list[DocumentChunk],
) -> Document:
    """Persist replacement chunks while the previous current set stays intact."""

    try:
        document = await _lock_document(session, document_id)
        await _discard_staged_chunks(session, document_id)
        session.add_all(stored_chunks)
        document.ingestion_status = IngestionStatus.PROCESSING
        document.ingestion_error = None
        document.ingestion_started_at = datetime.now(UTC)
        await session.commit()
        return document
    except Exception:
        await session.rollback()
        raise


async def _promote_staged_chunks(
    session: AsyncSession,
    document_id: uuid.UUID,
    staged_chunks: list[DocumentChunk],
    *,
    embedding_model: str,
) -> Document:
    """Atomically swap the staged replacement set into the current set.

    The previous current chunks are deleted only inside this transaction, after
    replacement embeddings have already been written. Deleting them cascades the
    previous vector rows. Any failure rolls the whole swap back, leaving the
    previous current chunks and embeddings intact.
    """

    try:
        document = await _lock_document(session, document_id)
        if document.ingestion_status is not IngestionStatus.PROCESSING:
            await session.rollback()
            raise DocumentNotReadyError(
                "Document ingestion was interrupted before indexing completed."
            )

        staged_ids = [chunk.id for chunk in staged_chunks]
        await session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.is_current.is_(True),
            )
        )
        await session.execute(
            update(DocumentChunk)
            .where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.id.in_(staged_ids),
                DocumentChunk.is_current.is_(False),
            )
            .values(is_current=True)
        )

        document.ingestion_status = IngestionStatus.READY
        document.ingestion_error = None
        document.ingestion_started_at = None
        document.ingested_at = datetime.now(UTC)
        document.embedding_model = embedding_model
        await session.commit()
        return document
    except Exception:
        await session.rollback()
        raise


async def _ingest_document_locked(
    session: AsyncSession,
    document_id: uuid.UUID,
    storage: DocumentStorage,
    vector_index: VectorIndex,
    *,
    max_pages: int,
    chunk_size: int,
    chunk_overlap: int,
    ingestion_version: str,
    prepared_documents: Sequence[LangChainDocument] | None,
) -> Document:
    document = await _mark_processing(session, document_id)

    try:
        if not document.storage_key:
            raise DocumentIngestionError(INGESTION_ERROR_STORAGE)

        size, checksum = await run_in_threadpool(
            measure_stored_object,
            storage,
            document.storage_key,
        )
        _verify_stored_metadata(document, size=size, checksum=checksum)

        if prepared_documents is not None:
            page_documents = list(prepared_documents)
        else:
            page_documents = await run_in_threadpool(
                load_stored_pdf_documents,
                storage,
                document.storage_key,
                max_pages=max_pages,
            )

        if not page_documents:
            raise DocumentIngestionError(INGESTION_ERROR_EMPTY)

        chunks = await run_in_threadpool(
            split_page_documents,
            page_documents,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if not chunks:
            raise DocumentIngestionError(INGESTION_ERROR_EMPTY)
    except PdfValidationError as exc:
        message = (
            INGESTION_ERROR_PAGES
            if exc.code == "document_page_limit"
            else INGESTION_ERROR_PARSE
        )
        return await _mark_failed(session, document_id, message)
    except DocumentIngestionError as exc:
        return await _mark_failed(session, document_id, exc.message)
    except Exception:  # noqa: BLE001
        logger.warning(
            "Document ingestion failed unexpectedly",
            extra={
                "event": "document_ingestion_failed",
                "document_id": str(document_id),
            },
        )
        return await _mark_failed(
            session,
            document_id,
            INGESTION_ERROR_UNEXPECTED,
        )

    staged_chunks = _build_staged_chunks(
        document_id,
        chunks,
        ingestion_version=ingestion_version,
    )

    # Generate embeddings before staging anything. A provider failure leaves the
    # previous current chunk and vector set completely untouched.
    try:
        embeddings = await vector_index.embed_chunks(staged_chunks)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Document embedding failed",
            extra={
                "event": "document_ingestion_embedding_failed",
                "document_id": str(document_id),
                "error_type": type(exc).__name__,
            },
        )
        return await _fail_ingestion(
            session,
            document_id,
            INGESTION_ERROR_EMBEDDING,
            exc,
        )

    try:
        await _stage_chunks(session, document_id, staged_chunks)
    except IngestionInProgressError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Document chunk persistence failed",
            extra={
                "event": "document_ingestion_persistence_failed",
                "document_id": str(document_id),
                "error_type": type(exc).__name__,
            },
        )
        return await _fail_ingestion(
            session,
            document_id,
            INGESTION_ERROR_UNEXPECTED,
            exc,
        )

    try:
        await vector_index.add_chunks(
            document_id=document_id,
            chunks=staged_chunks,
            embeddings=embeddings,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Document embedding storage failed",
            extra={
                "event": "document_ingestion_embedding_failed",
                "document_id": str(document_id),
                "error_type": type(exc).__name__,
            },
        )
        return await _fail_ingestion(
            session,
            document_id,
            INGESTION_ERROR_EMBEDDING,
            exc,
        )

    try:
        return await _promote_staged_chunks(
            session,
            document_id,
            staged_chunks,
            embedding_model=vector_index.embedding_model,
        )
    except IngestionInProgressError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Document indexing finalization failed",
            extra={
                "event": "document_ingestion_finalization_failed",
                "document_id": str(document_id),
                "error_type": type(exc).__name__,
            },
        )
        return await _fail_ingestion(
            session,
            document_id,
            INGESTION_ERROR_UNEXPECTED,
            exc,
        )


async def ingest_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    storage: DocumentStorage,
    vector_index: VectorIndex,
    *,
    max_pages: int,
    chunk_size: int,
    chunk_overlap: int,
    ingestion_version: str,
    prepared_documents: Sequence[LangChainDocument] | None = None,
) -> Document:
    async with advisory_lock(
        session,
        document_ingestion_lock_key(document_id),
        blocking=False,
    ) as acquired:
        if not acquired:
            raise IngestionInProgressError("Document ingestion is already in progress.")
        return await _ingest_document_locked(
            session,
            document_id,
            storage,
            vector_index,
            max_pages=max_pages,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            ingestion_version=ingestion_version,
            prepared_documents=prepared_documents,
        )


def _has_valid_storage_metadata(document: Document) -> bool:
    if not document.storage_key:
        return False
    if document.content_type != PDF_CONTENT_TYPE:
        return False
    if document.byte_size is None or document.byte_size < 1:
        return False
    return is_valid_sha256(document.checksum_sha256)


async def _verify_activation_integrity(
    storage: DocumentStorage,
    *,
    storage_key: str,
    byte_size: int | None,
    checksum_sha256: str | None,
) -> None:
    try:
        size, checksum = await run_in_threadpool(
            measure_stored_object,
            storage,
            storage_key,
        )
    except DocumentIngestionError as exc:
        raise DocumentNotReadyError(
            "Document file is not available for activation."
        ) from exc

    if byte_size is None or size != byte_size or checksum != checksum_sha256:
        raise DocumentIntegrityError(
            "The stored document does not match its recorded integrity metadata."
        )


async def activate_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    storage: DocumentStorage,
) -> Document:
    document = await _lock_document(session, document_id)
    if document.is_active:
        await session.commit()
        return document

    if document.ingestion_status is not IngestionStatus.READY:
        await session.rollback()
        raise DocumentNotReadyError(
            "Document must be successfully ingested before activation."
        )

    chunk_count = await session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.is_current.is_(True),
        )
    )
    if not chunk_count:
        await session.rollback()
        raise DocumentNotReadyError(
            "Document must have at least one chunk before activation."
        )

    if not _has_valid_storage_metadata(document):
        await session.rollback()
        raise DocumentNotReadyError("Document storage metadata is incomplete.")

    expected_key = document.storage_key
    expected_size = document.byte_size
    expected_checksum = document.checksum_sha256

    # Release the row lock and any transaction before filesystem I/O.
    await session.rollback()
    await _verify_activation_integrity(
        storage,
        storage_key=expected_key or "",
        byte_size=expected_size,
        checksum_sha256=expected_checksum,
    )

    document = await _lock_document(session, document_id)
    if document.is_active:
        await session.commit()
        return document
    if document.ingestion_status is not IngestionStatus.READY:
        await session.rollback()
        raise DocumentNotReadyError(
            "Document must be successfully ingested before activation."
        )
    if (
        document.storage_key != expected_key
        or document.byte_size != expected_size
        or document.checksum_sha256 != expected_checksum
    ):
        await session.rollback()
        raise DocumentIntegrityError(
            "Document integrity metadata changed during activation."
        )

    chunk_count = await session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.is_current.is_(True),
        )
    )
    if not chunk_count:
        await session.rollback()
        raise DocumentNotReadyError(
            "Document must have at least one chunk before activation."
        )

    document.is_active = True
    await session.commit()
    return document


async def deactivate_document(
    session: AsyncSession,
    document_id: uuid.UUID,
) -> Document:
    document = await _lock_document(session, document_id)
    document.is_active = False
    await session.commit()
    return document


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def recover_stale_processing_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    stale_after_seconds: int,
    force_unknown_age: bool = False,
    now: datetime | None = None,
) -> Document:
    """Recover a PROCESSING document only when its ingestion is provably stale.

    This fails closed if an ingestion lock is held by another process, if the
    document is not PROCESSING, or if its start time is unknown and the
    operator has not explicitly forced recovery. Previous chunks are preserved
    and the document is left inactive in FAILED state for re-ingestion.
    """

    reference = now or datetime.now(UTC)
    async with advisory_lock(
        session,
        document_ingestion_lock_key(document_id),
        blocking=False,
    ) as acquired:
        if not acquired:
            raise DocumentRecoveryError(
                "An ingestion is currently running for this document.",
                code="ingestion_in_progress",
            )

        document = await _lock_document(session, document_id)
        if document.ingestion_status is not IngestionStatus.PROCESSING:
            await session.rollback()
            raise DocumentRecoveryError(
                "Document is not in processing state.",
                code="not_processing",
            )

        started_at = document.ingestion_started_at
        if started_at is None:
            if not force_unknown_age:
                await session.rollback()
                raise DocumentRecoveryError(
                    "Ingestion start time is unknown; refusing to recover "
                    "without explicit force.",
                    code="unknown_start_time",
                )
        else:
            threshold = reference - timedelta(seconds=stale_after_seconds)
            if _as_utc(started_at) > threshold:
                await session.rollback()
                raise DocumentRecoveryError(
                    "Document ingestion is not stale yet.",
                    code="ingestion_active",
                )

        await _discard_staged_chunks(session, document_id)
        document.ingestion_status = IngestionStatus.FAILED
        document.ingestion_error = INGESTION_ERROR_RECOVERED
        document.ingestion_started_at = None
        document.is_active = False
        await session.commit()

        logger.warning(
            "Recovered stale document ingestion",
            extra={
                "event": "document_ingestion_recovered",
                "document_id": str(document_id),
                "stale_after_seconds": stale_after_seconds,
                "forced_unknown_age": force_unknown_age,
            },
        )
        return document
