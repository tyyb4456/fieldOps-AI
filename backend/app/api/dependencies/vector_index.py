from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from fastapi import Depends, status

from app.core.exceptions import AppError
from app.db.session import engine
from app.services.rag.embeddings import (
    EmbeddingConfigurationError,
    GoogleEmbeddingProvider,
    get_embedding_provider,
)
from app.services.rag.vector_index import DatabaseVectorIndex, VectorIndex

logger = logging.getLogger(__name__)


def get_embedding_service() -> GoogleEmbeddingProvider:
    try:
        return get_embedding_provider()
    except EmbeddingConfigurationError as exc:
        raise AppError(
            "Embedding service is not configured.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="embedding_unavailable",
        ) from exc


async def get_vector_index(
    embedding_provider: GoogleEmbeddingProvider = Depends(get_embedding_service),
) -> AsyncIterator[VectorIndex]:
    index = DatabaseVectorIndex(
        engine=engine,
        embedding_provider=embedding_provider,
        owns_engine=False,
    )
    try:
        yield index
    finally:
        await index.close()
