from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_operations_user
from app.api.dependencies.vector_index import get_vector_index
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.retrieval import (
    RetrievalResultResponse,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
from app.services import retrieval as retrieval_service
from app.services.embeddings import EmbeddingError
from app.services.vector_index import VectorIndex, VectorIndexError

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
