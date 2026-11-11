from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest
from langchain_core.embeddings import Embeddings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_chunk_embedding import DocumentChunkEmbedding
from app.models.enums import IngestionStatus
from app.services.document_ingestion import (
    INGESTION_ERROR_EMBEDDING,
    activate_document,
    ingest_document,
)
from app.services.retrieval import authorized_document_ids
from app.services.storage import LocalFileStorage
from app.services.vector_index import (
    DatabaseVectorIndex,
    VectorIndexError,
)
from tests.conftest import MigrationDatabase
from tests.pdf_factory import build_pdf


class KeywordEmbeddings(Embeddings):
    def __init__(self, *, model_name: str = "gemini-embedding-001") -> None:
        self.model_name = model_name
        self.fail = False

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * 1536
        if "alpha" in text.lower():
            vector[0] = 1.0
        elif "beta" in text.lower():
            vector[1] = 1.0
        else:
            vector[2] = 1.0
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise RuntimeError("embedding provider unavailable")
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        if self.fail:
            raise RuntimeError("embedding provider unavailable")
        return self._vector(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)


class PartialVectorIndex(DatabaseVectorIndex):
    """Writes one vector row and then fails, simulating a partial store write."""

    async def add_chunks(
        self,
        *,
        document_id: uuid.UUID,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        assert embeddings is not None
        await super().add_chunks(
            document_id=document_id,
            chunks=list(chunks)[:1],
            embeddings=list(embeddings)[:1],
        )
        raise VectorIndexError("vector store failed after a partial write")


def _vector_engine(database: MigrationDatabase) -> AsyncEngine:
    return create_async_engine(database.url, poolclass=NullPool)


def _storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "document_storage")


async def _seed_stored_document(
    session: AsyncSession,
    storage: LocalFileStorage,
    *,
    pages: list[str],
) -> Document:
    key = storage.generate_key("manual.pdf")
    data = build_pdf(pages)
    storage.save(key, data)
    document = Document(
        manufacturer="Acme Solar",
        model="INV-5000",
        document_name=f"Manual {uuid.uuid4().hex}",
        version="1.0",
        storage_key=key,
        original_filename="manual.pdf",
        content_type="application/pdf",
        byte_size=len(data),
        checksum_sha256=hashlib.sha256(data).hexdigest(),
        ingestion_status=IngestionStatus.PENDING,
        is_active=False,
    )
    session.add(document)
    await session.commit()
    return document


def _replace_pdf(
    session: AsyncSession,
    storage: LocalFileStorage,
    document: Document,
    *,
    pages: list[str],
) -> None:
    assert document.storage_key is not None
    data = build_pdf(pages)
    storage.save(document.storage_key, data, overwrite=True)
    document.byte_size = len(data)
    document.checksum_sha256 = hashlib.sha256(data).hexdigest()


async def _ingest(
    session: AsyncSession,
    storage: LocalFileStorage,
    document: Document,
    index: DatabaseVectorIndex,
) -> Document:
    return await ingest_document(
        session,
        document.id,
        storage,
        index,
        max_pages=10,
        chunk_size=1000,
        chunk_overlap=0,
        ingestion_version="1",
    )


async def _chunks(session: AsyncSession, document_id: uuid.UUID) -> list[DocumentChunk]:
    result = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(result.scalars().all())


async def _vectors(
    session: AsyncSession,
    document_id: uuid.UUID,
) -> list[DocumentChunkEmbedding]:
    result = await session.execute(
        select(DocumentChunkEmbedding).where(
            DocumentChunkEmbedding.document_id == document_id
        )
    )
    return list(result.scalars().all())


async def test_failed_replacement_embedding_preserves_chunks_and_vectors(
    committed_db_session: AsyncSession,
    committed_migration_database: MigrationDatabase,
    tmp_path: Path,
) -> None:
    storage = _storage(tmp_path)
    document = await _seed_stored_document(
        committed_db_session,
        storage,
        pages=["Alpha stable manual text"],
    )
    provider = KeywordEmbeddings()
    engine = _vector_engine(committed_migration_database)
    index = DatabaseVectorIndex(engine=engine, embedding_provider=provider)
    try:
        ingested = await _ingest(
            committed_db_session,
            storage,
            document,
            index,
        )
        assert ingested.ingestion_status is IngestionStatus.READY
        await activate_document(committed_db_session, document.id, storage)

        original_chunks = await _chunks(committed_db_session, document.id)
        original_vectors = await _vectors(committed_db_session, document.id)
        assert [chunk.content for chunk in original_chunks] == [
            "Alpha stable manual text"
        ]
        assert len(original_vectors) == 1
        original_chunk_ids = {chunk.id for chunk in original_chunks}
        original_vector_ids = {vector.id for vector in original_vectors}

        _replace_pdf(
            committed_db_session,
            storage,
            document,
            pages=["Beta replacement manual text"],
        )
        await committed_db_session.commit()
        provider.fail = True

        failed = await _ingest(
            committed_db_session,
            storage,
            document,
            index,
        )

        assert failed.ingestion_status is IngestionStatus.FAILED
        assert failed.ingestion_error == INGESTION_ERROR_EMBEDDING
        assert failed.is_active is False

        stored_chunks = await _chunks(committed_db_session, document.id)
        stored_vectors = await _vectors(committed_db_session, document.id)
        assert {chunk.id for chunk in stored_chunks} == original_chunk_ids
        assert [chunk.content for chunk in stored_chunks] == [
            "Alpha stable manual text"
        ]
        assert all(chunk.is_current for chunk in stored_chunks)
        assert {vector.id for vector in stored_vectors} == original_vector_ids
    finally:
        await index.close()
        await engine.dispose()


async def test_successful_replacement_swaps_chunks_and_vectors(
    committed_db_session: AsyncSession,
    committed_migration_database: MigrationDatabase,
    tmp_path: Path,
) -> None:
    storage = _storage(tmp_path)
    document = await _seed_stored_document(
        committed_db_session,
        storage,
        pages=["Alpha original manual text"],
    )
    provider = KeywordEmbeddings()
    engine = _vector_engine(committed_migration_database)
    index = DatabaseVectorIndex(engine=engine, embedding_provider=provider)
    try:
        await _ingest(committed_db_session, storage, document, index)
        await activate_document(committed_db_session, document.id, storage)

        original_chunks = await _chunks(committed_db_session, document.id)
        original_vectors = await _vectors(committed_db_session, document.id)
        original_chunk_ids = {chunk.id for chunk in original_chunks}
        original_vector_ids = {vector.id for vector in original_vectors}

        _replace_pdf(
            committed_db_session,
            storage,
            document,
            pages=["Beta replacement manual text"],
        )
        await committed_db_session.commit()

        replaced = await _ingest(
            committed_db_session,
            storage,
            document,
            index,
        )

        assert replaced.ingestion_status is IngestionStatus.READY
        assert replaced.is_active is False
        assert replaced.embedding_model == "gemini-embedding-001"

        stored_chunks = await _chunks(committed_db_session, document.id)
        stored_vectors = await _vectors(committed_db_session, document.id)
        assert [chunk.content for chunk in stored_chunks] == [
            "Beta replacement manual text"
        ]
        assert all(chunk.is_current for chunk in stored_chunks)
        assert {chunk.id for chunk in stored_chunks}.isdisjoint(original_chunk_ids)
        assert {vector.id for vector in stored_vectors} == {
            chunk.id for chunk in stored_chunks
        }
        assert {vector.id for vector in stored_vectors}.isdisjoint(
            original_vector_ids
        )
        assert {vector.embedding_model for vector in stored_vectors} == {
            "gemini-embedding-001"
        }

        permitted = await authorized_document_ids(committed_db_session)
        assert document.id not in permitted

        await activate_document(committed_db_session, document.id, storage)
        permitted = await authorized_document_ids(committed_db_session)
        assert document.id in permitted
    finally:
        await index.close()
        await engine.dispose()


async def test_partial_vector_write_does_not_expose_incomplete_replacement(
    committed_db_session: AsyncSession,
    committed_migration_database: MigrationDatabase,
    tmp_path: Path,
) -> None:
    storage = _storage(tmp_path)
    document = await _seed_stored_document(
        committed_db_session,
        storage,
        pages=["Alpha original page"],
    )
    provider = KeywordEmbeddings()
    engine = _vector_engine(committed_migration_database)
    index = DatabaseVectorIndex(engine=engine, embedding_provider=provider)
    try:
        await _ingest(committed_db_session, storage, document, index)
        await activate_document(committed_db_session, document.id, storage)

        original_chunks = await _chunks(committed_db_session, document.id)
        original_vectors = await _vectors(committed_db_session, document.id)
        original_chunk_ids = {chunk.id for chunk in original_chunks}
        original_vector_ids = {vector.id for vector in original_vectors}

        _replace_pdf(
            committed_db_session,
            storage,
            document,
            pages=["Beta replacement page one", "Beta replacement page two"],
        )
        await committed_db_session.commit()

        partial_index = PartialVectorIndex(
            engine=engine,
            embedding_provider=provider,
        )
        failed = await _ingest(
            committed_db_session,
            storage,
            document,
            partial_index,
        )

        assert failed.ingestion_status is IngestionStatus.FAILED
        assert failed.ingestion_error == INGESTION_ERROR_EMBEDDING
        assert failed.is_active is False

        stored_chunks = await _chunks(committed_db_session, document.id)
        stored_vectors = await _vectors(committed_db_session, document.id)
        assert {chunk.id for chunk in stored_chunks} == original_chunk_ids
        assert all(chunk.is_current for chunk in stored_chunks)
        assert {vector.id for vector in stored_vectors} == original_vector_ids
        assert len(stored_vectors) == len(original_vector_ids)

        permitted = await authorized_document_ids(committed_db_session)
        assert document.id not in permitted
    finally:
        await partial_index.close()
        await index.close()
        await engine.dispose()


async def test_correct_embedding_model_retrieves_existing_vectors(
    committed_db_session: AsyncSession,
    committed_migration_database: MigrationDatabase,
    tmp_path: Path,
) -> None:
    storage = _storage(tmp_path)
    document = await _seed_stored_document(
        committed_db_session,
        storage,
        pages=["Alpha searchable manual text"],
    )
    provider = KeywordEmbeddings()
    engine = _vector_engine(committed_migration_database)
    index = DatabaseVectorIndex(
        engine=engine,
        embedding_provider=provider,
        embedding_model="gemini-embedding-001",
    )
    try:
        await _ingest(committed_db_session, storage, document, index)
        await activate_document(committed_db_session, document.id, storage)

        hits = await index.search(
            query="alpha",
            document_ids=[document.id],
            k=5,
        )
    finally:
        await index.close()
        await engine.dispose()

    assert hits
    assert hits[0].distance == pytest.approx(0.0, abs=1e-6)
