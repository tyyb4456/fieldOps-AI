from __future__ import annotations

from app.core.config import settings
from app.services.agents.chat_model import get_chat_model
from app.services.rag.knowledge_answer import KnowledgeAnswerService


def get_knowledge_answer_service() -> KnowledgeAnswerService:
    """Construct the grounded answer service from application settings.

    The chat model factory is resolved lazily by the service so a request with
    no retrieved evidence can still return an insufficient-evidence response
    when the chat provider is not configured.
    """

    return KnowledgeAnswerService(
        chat_model_factory=get_chat_model,
        min_similarity=settings.answer_min_similarity,
        max_context_chars=settings.answer_max_context_chars,
    )
