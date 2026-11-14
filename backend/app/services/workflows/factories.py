from __future__ import annotations

from app.core.config import settings
from app.db.session import async_session_factory, engine
from app.services.agents.chat_model import get_chat_model
from app.services.diagnostics.diagnostics import DiagnosticService
from app.services.rag.embeddings import get_embedding_provider
from app.services.rag.vector_index import DatabaseVectorIndex
from app.services.work_orders.work_order_proposals import (
    WorkOrderProposalService,
)


def build_diagnostic_service() -> DiagnosticService:
    return DiagnosticService(
        chat_model_factory=get_chat_model,
        min_similarity=settings.answer_min_similarity,
        knowledge_top_k=settings.diagnostic_knowledge_top_k,
        max_service_records=settings.diagnostic_max_service_records,
        max_tool_calls=settings.diagnostic_max_tool_calls,
        max_model_calls=settings.diagnostic_max_model_calls,
        session_factory=async_session_factory,
    )


def build_work_order_proposal_service(
    *,
    diagnostic_service: DiagnosticService | None = None,
) -> WorkOrderProposalService:
    return WorkOrderProposalService(
        diagnostic_service=(
            diagnostic_service
            if diagnostic_service is not None
            else build_diagnostic_service()
        ),
        chat_model_factory=get_chat_model,
        max_tool_calls=settings.work_order_proposal_max_tool_calls,
        max_model_calls=settings.work_order_proposal_max_model_calls,
        technician_limit=settings.work_order_proposal_max_technicians,
    )


def build_vector_index() -> DatabaseVectorIndex:
    return DatabaseVectorIndex(
        engine=engine,
        embedding_provider=get_embedding_provider(),
        owns_engine=False,
    )


__all__ = [
    "build_diagnostic_service",
    "build_vector_index",
    "build_work_order_proposal_service",
]
