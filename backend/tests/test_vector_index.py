from __future__ import annotations

import uuid

import pytest
from langchain_core.embeddings import Embeddings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import IngestionStatus
from app.services.vector_index import (
    DatabaseVectorIndex,
    EmbeddingModelMismatchError,
    VectorIndexError,
)
from tests.conftest import MigrationDatabase


class KeywordEmbeddings(Embeddings):
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
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


async def _seed_document(
    session: AsyncSession,
    *,
    contents: tuple[str, ...],
) -> tuple[Document, list[DocumentChunk]]:
    document = Document(
        manufacturer="Acme Solar",
        model="INV-5000",
        document_name=f"Manual {uuid.uuid4().hex}",
        version="1.0",
        ingestion_status=IngestionStatus.READY,
        is_active=True,
    )
    session.add(document)
    await session.flush()
    chunks = [
        DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            content=content,
            page_number=1,
        )
        for index, content in enumerate(contents)
    ]
    session.add_all(chunks)
    await session.commit()
    return document, chunks


def _vector_engine(database: MigrationDatabase) -> AsyncEngine:
    return create_async_engine(
        database.url,
        poolclass=NullPool,
    )


async def test_database_vector_index_round_trips_and_filters_documents(
    committed_db_session: AsyncSession,
    committed_migration_database: MigrationDatabase,
) -> None:
    allowed, allowed_chunks = await _seed_document(
        committed_db_session,
        contents=("alpha allowed", "beta allowed"),
    )
    blocked, blocked_chunks = await _seed_document(
        committed_db_session,
        contents=("alpha blocked",),
    )

    engine = _vector_engine(committed_migration_database)
    index = DatabaseVectorIndex(
        engine=engine,
        embedding_provider=KeywordEmbeddings(),
    )
    try:
        await index.add_chunks(
            document_id=allowed.id,
            chunks=allowed_chunks,
        )
        await index.add_chunks(
            document_id=blocked.id,
            chunks=blocked_chunks,
        )

        hits = await index.search(
            query="alpha",
            document_ids=[allowed.id],
            k=10,
        )
    finally:
        await index.close()
        await engine.dispose()

    assert hits
    assert {hit.chunk_id for hit in hits} == {
        chunk.id for chunk in allowed_chunks
    }
    assert hits[0].chunk_id == allowed_chunks[0].id
    assert hits[0].distance == pytest.approx(0.0, abs=1e-6)


async def test_database_vector_index_stores_embedding_model_per_vector(
    committed_db_session: AsyncSession,
    committed_migration_database: MigrationDatabase,
) -> None:
    document, chunks = await _seed_document(
        committed_db_session,
        contents=("alpha allowed",),
    )
    engine = _vector_engine(committed_migration_database)
    index = DatabaseVectorIndex(
        engine=engine,
        embedding_provider=KeywordEmbeddings(),
        embedding_model="gemini-embedding-001",
    )
    try:
        await index.add_chunks(document_id=document.id, chunks=chunks)
        async with engine.connect() as connection:
            models = (
                await connection.execute(
                    text(
                        'SELECT DISTINCT "embedding_model" FROM "document_chunk_embeddings" '
                        'WHERE "document_id" = :document_id'
                    ),
                    {"document_id": document.id},
                )
            ).scalars().all()
    finally:
        await index.close()
        await engine.dispose()

    assert list(models) == ["gemini-embedding-001"]


async def test_incompatible_embedding_model_cannot_query_old_vectors(
    committed_db_session: AsyncSession,
    committed_migration_database: MigrationDatabase,
) -> None:
    document, chunks = await _seed_document(
        committed_db_session,
        contents=("alpha allowed",),
    )
    engine = _vector_engine(committed_migration_database)
    old_index = DatabaseVectorIndex(
        engine=engine,
        embedding_provider=KeywordEmbeddings(),
        embedding_model="gemini-embedding-old",
    )
    new_index = DatabaseVectorIndex(
        engine=engine,
        embedding_provider=KeywordEmbeddings(),
        embedding_model="gemini-embedding-001",
    )
    try:
        await old_index.add_chunks(document_id=document.id, chunks=chunks)
        with pytest.raises(EmbeddingModelMismatchError) as error:
            await new_index.search(
                query="alpha",
                document_ids=[document.id],
                k=10,
            )
    finally:
        await old_index.close()
        await new_index.close()
        await engine.dispose()

    assert error.value.stored_model == "gemini-embedding-old"
    assert error.value.expected_model == "gemini-embedding-001"


async def test_shared_engine_remains_usable_after_vector_store_close(
    committed_migration_database: MigrationDatabase,
) -> None:
    engine = _vector_engine(committed_migration_database)
    index = DatabaseVectorIndex(
        engine=engine,
        embedding_provider=KeywordEmbeddings(),
        owns_engine=False,
    )
    try:
        await index.search(query="alpha", document_ids=[], k=5)
        await index.close()
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    finally:
        await engine.dispose()


async def test_database_vector_index_skips_empty_document_scope(
    committed_migration_database: MigrationDatabase,
) -> None:
    engine = _vector_engine(committed_migration_database)
    index = DatabaseVectorIndex(
        engine=engine,
        embedding_provider=KeywordEmbeddings(),
    )
    try:
        hits = await index.search(
            query="alpha",
            document_ids=[],
            k=5,
        )
    finally:
        await index.close()
        await engine.dispose()

    assert hits == []


async def test_database_vector_index_rejects_invalid_chunks(
    committed_migration_database: MigrationDatabase,
) -> None:
    document_id = uuid.uuid4()
    engine = _vector_engine(committed_migration_database)
    index = DatabaseVectorIndex(
        engine=engine,
        embedding_provider=KeywordEmbeddings(),
    )
    try:
        blank = DocumentChunk(
            document_id=document_id,
            chunk_index=0,
            content="   ",
        )
        with pytest.raises(VectorIndexError, match="Empty"):
            await index.add_chunks(document_id=document_id, chunks=[blank])

        duplicate = DocumentChunk(
            id=uuid.uuid4(),
            document_id=document_id,
            chunk_index=0,
            content="alpha",
        )
        with pytest.raises(VectorIndexError, match="Duplicate"):
            await index.add_chunks(
                document_id=document_id,
                chunks=[duplicate, duplicate],
            )

        other = DocumentChunk(
            document_id=uuid.uuid4(),
            chunk_index=0,
            content="alpha",
        )
        with pytest.raises(VectorIndexError, match="does not belong"):
            await index.add_chunks(document_id=document_id, chunks=[other])
    finally:
        await index.close()
        await engine.dispose()
