from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_operations_user
from app.api.dependencies.knowledge_answer import get_knowledge_answer_service
from app.api.dependencies.vector_index import get_vector_index
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.rag.knowledge_answer import (
    CitationResponse,
    KnowledgeAnswerRequest,
    KnowledgeAnswerResponse,
)
from app.schemas.rag.retrieval import (
    RetrievalResultResponse,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
from app.services.rag import retrieval as retrieval_service
from app.services.rag.embeddings import EmbeddingError
from app.services.rag.knowledge_answer import (
    AnswerGenerationError,
    KnowledgeAnswerService,
)
from app.services.rag.vector_index import VectorIndex, VectorIndexError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


@router.post(
    "/search",
    response_model=RetrievalSearchResponse,
    summary="Search active technical documentation",
)
async def search_knowledge_base(
    payload: RetrievalSearchRequest,
    user: User = Depends(require_operations_user),
    session: AsyncSession = Depends(get_db_session),
    vector_index: VectorIndex = Depends(get_vector_index),
) -> RetrievalSearchResponse:
    try:
        results = await retrieval_service.search_documents(
            session,
            user,
            vector_index=vector_index,
            query=payload.query,
            manufacturer=payload.manufacturer,
            model=payload.model,
            top_k=payload.top_k,
        )
    except (VectorIndexError, EmbeddingError) as exc:
        logger.warning(
            "Knowledge base search unavailable",
            extra={
                "event": "knowledge_base_search_unavailable",
                "error_type": type(exc).__name__,
            },
        )
        raise AppError(
            "Knowledge base search is unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="retrieval_unavailable",
        ) from exc

    return RetrievalSearchResponse(
        items=[
            RetrievalResultResponse(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                document_name=item.document_name,
                manufacturer=item.manufacturer,
                model=item.model,
                version=item.version,
                page_number=item.page_number,
                chunk_index=item.chunk_index,
                content=item.content,
                distance=item.distance,
                similarity=item.similarity,
            )
            for item in results
        ],
        top_k=payload.top_k,
    )


@router.post(
    "/answer",
    response_model=KnowledgeAnswerResponse,
    summary="Answer a technical question from indexed documentation",
)
async def answer_knowledge_question(
    payload: KnowledgeAnswerRequest,
    user: User = Depends(require_operations_user),
    session: AsyncSession = Depends(get_db_session),
    vector_index: VectorIndex = Depends(get_vector_index),
    answer_service: KnowledgeAnswerService = Depends(get_knowledge_answer_service),
) -> KnowledgeAnswerResponse:
    try:
        result = await answer_service.answer(
            session=session,
            user=user,
            vector_index=vector_index,
            question=payload.question,
            manufacturer=payload.manufacturer,
            model=payload.model,
            top_k=payload.top_k,
        )
    except (VectorIndexError, EmbeddingError) as exc:
        logger.warning(
            "Knowledge answer retrieval unavailable",
            extra={
                "event": "knowledge_answer_retrieval_unavailable",
                "error_type": type(exc).__name__,
            },
        )
        raise AppError(
            "Knowledge base search is unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="retrieval_unavailable",
        ) from exc
    except AnswerGenerationError as exc:
        logger.warning(
            "Knowledge answer generation unavailable",
            extra={
                "event": "knowledge_answer_generation_unavailable",
                "error_type": type(exc).__name__,
            },
        )
        raise AppError(
            "Answer generation is unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="answer_model_unavailable",
        ) from exc

    return KnowledgeAnswerResponse(
        answer=result.answer,
        status=result.status,
        citations=[
            CitationResponse(
                source_id=citation.source_id,
                chunk_id=citation.chunk_id,
                document_id=citation.document_id,
                document_name=citation.document_name,
                manufacturer=citation.manufacturer,
                model=citation.model,
                version=citation.version,
                page_number=citation.page_number,
                chunk_index=citation.chunk_index,
                excerpt=citation.excerpt,
            )
            for citation in result.citations
        ],
        evidence_summary=result.evidence_summary,
        insufficient_evidence=result.insufficient_evidence,
        missing_information=list(result.missing_information),
        warnings=list(result.warnings),
    )
