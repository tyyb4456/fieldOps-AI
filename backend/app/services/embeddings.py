from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from pydantic import SecretStr

from app.core.config import settings

logger = logging.getLogger(__name__)

DOCUMENT_TASK_TYPE = "RETRIEVAL_DOCUMENT"
QUERY_TASK_TYPE = "RETRIEVAL_QUERY"


class EmbeddingError(Exception):
    """Base class for embedding failures safe to translate at API boundaries."""


class EmbeddingConfigurationError(EmbeddingError):
    pass


class EmbeddingGenerationError(EmbeddingError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class GoogleEmbeddingProvider(Embeddings):
    """Gemini embeddings with explicit retrieval task types.

    Document and query embeddings must come from the same model and output
    dimensionality. Task types are fixed by this class rather than accepted
    from request data so callers cannot accidentally mix incompatible
    embedding spaces.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
    ) -> None:
        key = api_key.strip()
        if not key:
            raise EmbeddingConfigurationError(
                "GOOGLE_API_KEY is required to generate embeddings."
            )
        self._model_name = model.strip()
        if not self._model_name:
            raise EmbeddingConfigurationError(
                "EMBEDDING_MODEL is required to generate embeddings."
            )
        if dimensions < 1:
            raise EmbeddingConfigurationError(
                "EMBEDDING_DIMENSIONS must be a positive integer."
            )
        self._dimensions = dimensions
        self._model = GoogleGenerativeAIEmbeddings(
            model=self._model_name,
            google_api_key=SecretStr(key),
        )

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.embed_documents(
            texts,
            task_type=DOCUMENT_TASK_TYPE,
            output_dimensionality=self._dimensions,
        )
        return self._validate_vectors(vectors, expected_count=len(texts))

    def embed_query(self, text: str) -> list[float]:
        vector = self._model.embed_query(
            text,
            task_type=QUERY_TASK_TYPE,
            output_dimensionality=self._dimensions,
        )
        return self._validate_vector(vector)[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            vectors = await self._model.aembed_documents(
                texts,
                task_type=DOCUMENT_TASK_TYPE,
                output_dimensionality=self._dimensions,
            )
        except Exception as exc:
            self._log_failure("document", exc)
            raise EmbeddingGenerationError(
                "The document could not be embedded."
            ) from exc
        return self._validate_vectors(vectors, expected_count=len(texts))

    async def aembed_query(self, text: str) -> list[float]:
        try:
            vector = await self._model.aembed_query(
                text,
                task_type=QUERY_TASK_TYPE,
                output_dimensionality=self._dimensions,
            )
        except Exception as exc:
            self._log_failure("query", exc)
            raise EmbeddingGenerationError(
                "The search query could not be embedded."
            ) from exc
        return self._validate_vector(vector)[0]

    def _log_failure(self, kind: str, exc: Exception) -> None:
        logger.warning(
            "Embedding request failed",
            extra={
                "event": "embedding_request_failed",
                "embedding_kind": kind,
                "embedding_model": self._model_name,
                "error_type": type(exc).__name__,
            },
        )

    def _validate_vectors(
        self,
        vectors: Sequence[Sequence[object]],
        *,
        expected_count: int,
    ) -> list[list[float]]:
        if len(vectors) != expected_count:
            raise EmbeddingGenerationError(
                "Embedding provider returned an unexpected number of vectors."
            )
        return [self._validate_vector(vector)[0] for vector in vectors]

    def _validate_vector(self, vector: Sequence[object]) -> list[list[float]]:
        if len(vector) != self._dimensions:
            raise EmbeddingGenerationError(
                "Embedding provider returned an unexpected vector dimension."
            )
        normalized: list[float] = []
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EmbeddingGenerationError(
                    "Embedding provider returned an invalid vector value."
                )
            numeric = float(value)
            if not math.isfinite(numeric):
                raise EmbeddingGenerationError(
                    "Embedding provider returned a non-finite vector value."
                )
            normalized.append(numeric)
        return [normalized]


@lru_cache(maxsize=4)
def _build_embedding_provider(
    api_key: str,
    model: str,
    dimensions: int,
) -> GoogleEmbeddingProvider:
    return GoogleEmbeddingProvider(
        api_key=api_key,
        model=model,
        dimensions=dimensions,
    )


def get_embedding_provider() -> GoogleEmbeddingProvider:
    api_key = settings.google_api_key
    if not api_key:
        raise EmbeddingConfigurationError(
            "Embedding service is not configured."
        )
    return _build_embedding_provider(
        api_key,
        settings.embedding_model,
        settings.embedding_dimensions,
    )
