from __future__ import annotations

from typing import Any, ClassVar

import pytest

import app.services.embeddings as embeddings_module
from app.core.config import settings
from app.services.embeddings import (
    DOCUMENT_TASK_TYPE,
    QUERY_TASK_TYPE,
    EmbeddingConfigurationError,
    EmbeddingGenerationError,
    GoogleEmbeddingProvider,
    get_embedding_provider,
)


class FakeGoogleEmbeddings:
    instances: ClassVar[list[FakeGoogleEmbeddings]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.document_calls: list[tuple[list[str], str | None, int | None]] = []
        self.query_calls: list[tuple[str, str | None, int | None]] = []
        self.vectors: list[list[float]] = []
        self.query_vector: list[float] = []
        FakeGoogleEmbeddings.instances.append(self)

    async def aembed_documents(
        self,
        texts: list[str],
        *,
        task_type: str | None = None,
        output_dimensionality: int | None = None,
    ) -> list[list[float]]:
        self.document_calls.append((texts, task_type, output_dimensionality))
        return self.vectors

    async def aembed_query(
        self,
        text: str,
        *,
        task_type: str | None = None,
        output_dimensionality: int | None = None,
    ) -> list[float]:
        self.query_calls.append((text, task_type, output_dimensionality))
        return self.query_vector


def _provider(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dimensions: int = 3,
) -> tuple[GoogleEmbeddingProvider, FakeGoogleEmbeddings]:
    FakeGoogleEmbeddings.instances.clear()
    monkeypatch.setattr(
        embeddings_module,
        "GoogleGenerativeAIEmbeddings",
        FakeGoogleEmbeddings,
    )
    provider = GoogleEmbeddingProvider(
        api_key="test-key",
        model="gemini-embedding-001",
        dimensions=dimensions,
    )
    return provider, FakeGoogleEmbeddings.instances[0]


async def test_document_embeddings_use_retrieval_document_task_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, model = _provider(monkeypatch)
    model.vectors = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]

    vectors = await provider.aembed_documents(["alpha", "beta"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert model.document_calls == [
        (["alpha", "beta"], DOCUMENT_TASK_TYPE, 3)
    ]
    assert model.kwargs["model"] == "gemini-embedding-001"


async def test_query_embeddings_use_retrieval_query_task_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, model = _provider(monkeypatch)
    model.query_vector = [0.0, 0.0, 1.0]

    vector = await provider.aembed_query("error code")

    assert vector == [0.0, 0.0, 1.0]
    assert model.query_calls == [("error code", QUERY_TASK_TYPE, 3)]


async def test_embedding_dimension_mismatch_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, model = _provider(monkeypatch)
    model.vectors = [[1.0, 0.0]]

    with pytest.raises(EmbeddingGenerationError, match="dimension"):
        await provider.aembed_documents(["alpha"])


async def test_non_finite_embedding_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, model = _provider(monkeypatch)
    model.vectors = [[1.0, float("nan"), 0.0]]

    with pytest.raises(EmbeddingGenerationError, match="non-finite"):
        await provider.aembed_documents(["alpha"])


async def test_embedding_provider_errors_do_not_leak_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, model = _provider(monkeypatch)

    async def fail(*args: object, **kwargs: object) -> list[list[float]]:
        raise RuntimeError("provider secret detail")

    monkeypatch.setattr(model, "aembed_documents", fail)

    with pytest.raises(EmbeddingGenerationError) as error:
        await provider.aembed_documents(["alpha"])

    assert "provider secret detail" not in str(error.value)


def test_embedding_provider_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(EmbeddingConfigurationError):
        GoogleEmbeddingProvider(
            api_key="   ",
            model="gemini-embedding-001",
            dimensions=3,
        )

    monkeypatch.setattr(settings, "google_api_key", None)
    with pytest.raises(EmbeddingConfigurationError):
        get_embedding_provider()
