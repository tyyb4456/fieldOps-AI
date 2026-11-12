from __future__ import annotations

from app.core.config import settings
from app.db.session import async_session_factory
from app.services.chat_model import get_chat_model
from app.services.diagnostics import DiagnosticService


def get_diagnostic_service() -> DiagnosticService:
    """Construct the diagnostic service from application settings.

    The chat model factory and agent are resolved per request so the provider is
    only initialized when an investigation actually runs, and so tests can
    override this dependency without touching global state.
    """

    return DiagnosticService(
        chat_model_factory=get_chat_model,
        min_similarity=settings.answer_min_similarity,
        knowledge_top_k=settings.diagnostic_knowledge_top_k,
        max_service_records=settings.diagnostic_max_service_records,
        max_tool_calls=settings.diagnostic_max_tool_calls,
        max_model_calls=settings.diagnostic_max_model_calls,
        session_factory=async_session_factory,
    )
