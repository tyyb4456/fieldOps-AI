from __future__ import annotations

import asyncio
import logging
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from langchain_core.embeddings import Embeddings
from langchain_postgres import PGEngine, PGVectorStore
from langchain_postgres.v2.indexes import DistanceStrategy
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings
from app.models.document_chunk import DocumentChunk
from app.models.document_chunk_embedding import (
    VECTOR_TABLE_NAME,
)
from app.services.embeddings import EmbeddingError

logger = logging.getLogger(__name__)

VECTOR_SCHEMA_NAME = "public"
VECTOR_ID_COLUMN = "id"
VECTOR_CONTENT_COLUMN = "content"
VECTOR_EMBEDDING_COLUMN = "embedding"
VECTOR_METADATA_COLUMNS = ("document_id", "embedding_model")


class VectorIndexError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EmbeddingModelMismatchError(VectorIndexError):
    def __init__(
        self,
        message: str,
        *,
        stored_model: str,
        expected_model: str,
    ) -> None:
        super().__init__(message)
        self.stored_model = stored_model
        self.expected_model = expected_model


@dataclass(frozen=True)
class VectorSearchHit:
    chunk_id: uuid.UUID
    distance: float


class VectorIndex(Protocol):
    @property
    def embedding_model(self) -> str: ...

    async def embed_chunks(
        self,
        chunks: Sequence[object],
    ) -> list[list[float]]: ...

    async def add_chunks(
        self,
        *,
        document_id: uuid.UUID,
        chunks: Sequence[DocumentChunk],
        embeddings: Sequence[Sequence[float]] | None = None,
    ) -> None: ...

    async def search(
        self,
        *,
        query: str,
        document_ids: Sequence[uuid.UUID],
        k: int,
    ) -> list[VectorSearchHit]: ...

    async def close(self) -> None: ...


class DatabaseVectorIndex:
    """LangChain pgvector store backed by the application's database.

    The vector table is owned by Alembic. This class only performs vector
    writes and reads; document/chunk authorization remains authoritative in
    PostgreSQL application tables.
    """

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        embedding_provider: Embeddings,
        embedding_model: str | None = None,
        owns_engine: bool = True,
    ) -> None:
        self._engine = engine
        self._embedding_provider = embedding_provider
        provider_model = getattr(embedding_provider, "model_name", None)
        if not isinstance(provider_model, str) or not provider_model:
            provider_model = None
        if embedding_model and provider_model and embedding_model != provider_model:
            raise VectorIndexError(
                "The embedding index model must match the embedding provider model."
            )
        self._embedding_model: str = (
            embedding_model or provider_model or settings.embedding_model
        )
        self._pg_engine = PGEngine.from_engine(engine)
        self._owns_engine = owns_engine
        self._store: PGVectorStore | None = None
        self._store_lock = asyncio.Lock()

    @property
    def embedding_model(self) -> str:
        return self._embedding_model

    async def _get_store(self) -> PGVectorStore:
        if self._store is not None:
            return self._store
        async with self._store_lock:
            if self._store is None:
                self._store = await PGVectorStore.create(
                    self._pg_engine,
                    self._embedding_provider,
                    VECTOR_TABLE_NAME,
                    schema_name=VECTOR_SCHEMA_NAME,
                    content_column=VECTOR_CONTENT_COLUMN,
                    embedding_column=VECTOR_EMBEDDING_COLUMN,
                    metadata_columns=list(VECTOR_METADATA_COLUMNS),
                    id_column=VECTOR_ID_COLUMN,
                    distance_strategy=DistanceStrategy.COSINE_DISTANCE,
                )
        return self._store

    async def embed_chunks(
        self,
        chunks: Sequence[object],
    ) -> list[list[float]]:
        if not chunks:
            return []
        texts = [
            getattr(chunk, "content", "")
            for chunk in chunks
        ]
        try:
            return await self._embedding_provider.aembed_documents(texts)
        except EmbeddingError:
            raise
        except Exception as exc:
            logger.warning(
                "Document embedding generation failed",
                extra={
                    "event": "document_embedding_failed",
                    "error_type": type(exc).__name__,
                },
            )
            raise VectorIndexError(
                "Document embeddings could not be generated."
            ) from exc

    async def add_chunks(
        self,
        *,
        document_id: uuid.UUID,
        chunks: Sequence[DocumentChunk],
        embeddings: Sequence[Sequence[float]] | None = None,
    ) -> None:
        if not chunks:
            return

        chunk_ids = [chunk.id for chunk in chunks]
        if len(set(chunk_ids)) != len(chunk_ids):
            raise VectorIndexError("Duplicate chunk identifiers cannot be indexed.")
        for chunk in chunks:
            if chunk.document_id != document_id:
                raise VectorIndexError(
                    "Chunk does not belong to the requested document."
                )
            if not chunk.content.strip():
                raise VectorIndexError("Empty chunks cannot be indexed.")

        texts = [chunk.content for chunk in chunks]
        if embeddings is None:
            embeddings_list = await self.embed_chunks(chunks)
        else:
            embeddings_list = [list(vec) for vec in embeddings]

        if len(embeddings_list) != len(chunks):
            raise VectorIndexError(
                "Embedding provider returned an unexpected number of vectors."
            )

        metadatas = [
            {
                "document_id": str(document_id),
                "embedding_model": self._embedding_model,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
            }
            for chunk in chunks
        ]
        try:
            store = await self._get_store()
            await store.aadd_embeddings(
                texts=texts,
                embeddings=embeddings_list,
                metadatas=metadatas,
                ids=[str(chunk.id) for chunk in chunks],
            )
        except Exception as exc:
            logger.warning(
                "Document embeddings could not be stored",
                extra={
                    "event": "document_embedding_storage_failed",
                    "document_id": str(document_id),
                    "error_type": type(exc).__name__,
                },
            )
            raise VectorIndexError(
                "Document embeddings could not be stored."
            ) from exc

    async def validate_embedding_models(
        self,
        document_ids: Sequence[uuid.UUID],
    ) -> None:
        """Fail closed if any stored vector uses a different embedding model.

        Matching vector dimensions do not prove two embedding models share a
        compatible vector space. Any vector row written by another model must be
        rejected rather than silently mixed into a similarity search.
        """

        unique_document_ids = list(dict.fromkeys(document_ids))
        if not unique_document_ids:
            return

        query = text(
            f'SELECT DISTINCT "embedding_model" FROM '
            f'"{VECTOR_SCHEMA_NAME}"."{VECTOR_TABLE_NAME}" '
            f'WHERE "document_id" IN :document_ids'
        ).bindparams(bindparam("document_ids", expanding=True))
        async with self._engine.connect() as conn:
            result = await conn.execute(
                query,
                {"document_ids": unique_document_ids},
            )
            models = {model for model in result.scalars().all() if model}

        mismatched = sorted(model for model in models if model != self._embedding_model)
        if mismatched:
            stored_model = ", ".join(mismatched)
            logger.warning(
                "Stored vectors use an incompatible embedding model",
                extra={
                    "event": "embedding_model_mismatch",
                    "stored_model": stored_model,
                    "expected_model": self._embedding_model,
                    "document_count": len(unique_document_ids),
                },
            )
            raise EmbeddingModelMismatchError(
                "Stored vectors use an embedding model that does not match the "
                f"configured '{self._embedding_model}' model.",
                stored_model=stored_model,
                expected_model=self._embedding_model,
            )

    async def validate_document_model(self, document_id: uuid.UUID) -> bool:
        """Verify that stored vectors for document_id match the index's embedding model."""
        await self.validate_embedding_models([document_id])
        return True

    async def search(
        self,
        *,
        query: str,
        document_ids: Sequence[uuid.UUID],
        k: int,
    ) -> list[VectorSearchHit]:
        normalized_query = query.strip()
        if not normalized_query:
            raise VectorIndexError("Search query must not be blank.")
        if k < 1:
            raise VectorIndexError("Search result count must be positive.")

        unique_document_ids = list(dict.fromkeys(document_ids))
        if not unique_document_ids:
            return []

        await self.validate_embedding_models(unique_document_ids)

        try:
            store = await self._get_store()
            results = await store.asimilarity_search_with_score(
                normalized_query,
                k=k,
                filter={
                    "document_id": {
                        "$in": [str(item) for item in unique_document_ids]
                    },
                    "embedding_model": self._embedding_model,
                },
            )
        except Exception as exc:
            logger.warning(
                "Vector search failed",
                extra={
                    "event": "vector_search_failed",
                    "error_type": type(exc).__name__,
                },
            )
            raise VectorIndexError("Knowledge base search is unavailable.") from exc

        hits: list[VectorSearchHit] = []
        for document, distance in results:
            try:
                chunk_id = uuid.UUID(str(document.id))
            except (TypeError, ValueError):
                logger.warning(
                    "Vector search returned an invalid chunk identifier",
                    extra={"event": "invalid_vector_chunk_id"},
                )
                continue
            numeric_distance = float(distance)
            if not math.isfinite(numeric_distance):
                logger.warning(
                    "Vector search returned an invalid distance",
                    extra={"event": "invalid_vector_distance"},
                )
                continue
            hits.append(
                VectorSearchHit(
                    chunk_id=chunk_id,
                    distance=numeric_distance,
                )
            )

        hits.sort(key=lambda hit: hit.distance)
        return hits

    async def close(self) -> None:
        if self._owns_engine:
            await self._pg_engine.close()
