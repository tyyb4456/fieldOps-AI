from __future__ import annotations

import logging
from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import settings

logger = logging.getLogger(__name__)


class ChatModelConfigurationError(Exception):
    """Raised when the configured chat provider cannot be initialized."""


@lru_cache(maxsize=4)
def _build_chat_model(
    api_key: str,
    model: str,
    temperature: float,
    timeout_seconds: float,
    max_retries: int,
    max_output_tokens: int,
) -> BaseChatModel:
    return ChatOpenAI(
        model=model,
        api_key=SecretStr(api_key),
        temperature=temperature,
        timeout=timeout_seconds,
        max_retries=max_retries,
        max_completion_tokens=max_output_tokens,
    )


def get_chat_model() -> BaseChatModel:
    """Return the configured OpenAI chat model.

    The API key is read from application settings and wrapped in ``SecretStr``
    so it is never logged or included in error messages. The model instance is
    cached per configuration so the underlying client is not rebuilt for every
    request.
    """

    api_key = settings.openai_api_key
    if not api_key:
        raise ChatModelConfigurationError(
            "OPENAI_API_KEY is required for grounded answer generation."
        )

    logger.debug(
        "Building chat model",
        extra={
            "event": "chat_model_initialized",
            "chat_model": settings.chat_model,
        },
    )
    return _build_chat_model(
        api_key,
        settings.chat_model,
        settings.chat_temperature,
        settings.chat_timeout_seconds,
        settings.chat_max_retries,
        settings.chat_max_output_tokens,
    )
