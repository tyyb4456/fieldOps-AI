from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import async_session_factory
from app.models.complaint import Complaint
from app.models.equipment import Equipment
from app.models.user import User
from app.models.work_order import WorkOrder
from app.schemas.diagnostic import DiagnosticStatus
from app.services.authorization import (
    AccessDeniedError,
    is_admin,
    is_technician,
    scope_work_orders_for_user,
)
from app.services.chat_model import ChatModelConfigurationError
from app.services.diagnostic_agent import (
    DiagnosticCollector,
    DiagnosticContext,
    ModelDiagnosis,
    ModelDiagnosticCitation,
    build_diagnostic_agent,
    build_diagnostic_tools,
    build_investigation_message,
    compute_missing_information,
)
from app.services.equipment import get_equipment_for_customer
from app.services.knowledge_answer import Citation
from app.services.vector_index import VectorIndex

logger = logging.getLogger(__name__)

REVIEW_STATUSES = frozenset(
    {
        DiagnosticStatus.INSUFFICIENT_EVIDENCE,
        DiagnosticStatus.CONFLICTING_EVIDENCE,
    }
)

DEFAULT_ESCALATION_REASONS = {
    DiagnosticStatus.INSUFFICIENT_EVIDENCE: (
        "The available evidence is insufficient for a reliable diagnosis; "
        "human technical review is required."
    ),
    DiagnosticStatus.CONFLICTING_EVIDENCE: (
        "The available sources conflict; human technical review is required."
    ),
}


class DiagnosticError(Exception):
    """Base class for safe-to-translate diagnostic failures."""


class DiagnosticAgentUnavailableError(DiagnosticError):
    """The model or agent could not complete the investigation."""


class DiagnosticRetrievalUnavailableError(DiagnosticError):
    """The knowledge retrieval layer failed during the investigation."""


@dataclass(frozen=True)
class DiagnosticCause:
    cause: str
    basis: str
    evidence_chunk_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class DiagnosticCheck:
    step: str
    safety_note: str | None
    evidence_chunk_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class DiagnosticResult:
    complaint_id: uuid.UUID
    status: DiagnosticStatus
    summary: str
    probable_causes: tuple[DiagnosticCause, ...]
    recommended_checks: tuple[DiagnosticCheck, ...]
    missing_information: tuple[str, ...]
    safety_warnings: tuple[str, ...]
    conflicting_evidence_notes: tuple[str, ...]
    requires_escalation: bool
    escalation_reason: str | None
    citations: tuple[Citation, ...]
    warnings: tuple[str, ...]


async def get_complaint_for_operations_user(
    session: AsyncSession,
    user: User,
    complaint_id: uuid.UUID,
) -> Complaint:
    """Load a complaint the caller may investigate.

    Administrators may investigate any complaint. Technicians may investigate a
    complaint only when a work order for it is visible to them through an active
    assignment. Customers and unknown roles are denied. Failures are reported as
    ``AccessDeniedError`` so the API returns a non-probing 404.
    """

    if is_admin(user):
        statement = select(Complaint).where(Complaint.id == complaint_id)
    elif is_technician(user):
        visible_work_order = (
            scope_work_orders_for_user(user)
            .where(WorkOrder.complaint_id == complaint_id)
            .exists()
        )
        statement = select(Complaint).where(
            Complaint.id == complaint_id,
            visible_work_order,
        )
    else:
        raise AccessDeniedError("Complaint not found")

    complaint = (await session.execute(statement)).scalar_one_or_none()
    if complaint is None:
        raise AccessDeniedError("Complaint not found")
    return complaint


def _parse_chunk_id(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value).strip())
    except (TypeError, ValueError):
        return None


def _build_citations(
    references: list[ModelDiagnosticCitation],
    collector: DiagnosticCollector,
) -> tuple[list[Citation], int, int]:
    citations: list[Citation] = []
    seen: set[uuid.UUID] = set()
    dropped = 0
    duplicates = 0

    for reference in references:
        chunk_id = _parse_chunk_id(reference.chunk_id)
        chunk = collector.get(chunk_id) if chunk_id is not None else None
        if chunk is None:
            dropped += 1
            continue
        if chunk.chunk_id in seen:
            duplicates += 1
            continue
        seen.add(chunk.chunk_id)
        citations.append(
            Citation(
                source_id=f"S{len(citations) + 1}",
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                manufacturer=chunk.manufacturer,
                model=chunk.model,
                version=chunk.version,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                excerpt=chunk.content,
            )
        )

    return citations, dropped, duplicates


def _validate_evidence_ids(
    values: list[str],
    collector: DiagnosticCollector,
) -> tuple[tuple[uuid.UUID, ...], int]:
    valid: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    dropped = 0

    for value in values:
        chunk_id = _parse_chunk_id(value)
        if chunk_id is None or collector.get(chunk_id) is None:
            dropped += 1
            continue
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        valid.append(chunk_id)

    return tuple(valid), dropped


def _merge_missing_information(
    deterministic: tuple[str, ...],
    model_values: list[str],
) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in (*deterministic, *model_values):
        normalized = item.strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        merged.append(normalized)
    return tuple(merged)


def finalize_diagnosis(
    diagnosis: ModelDiagnosis,
    *,
    complaint_id: uuid.UUID,
    collector: DiagnosticCollector,
    deterministic_missing_information: tuple[str, ...],
) -> DiagnosticResult:
    """Validate model output and construct the application-owned result.

    Citation metadata is copied from chunks actually returned by the knowledge
    tool. Unknown or duplicate identifiers are removed. A diagnosis without any
    valid documentation citation is downgraded to insufficient evidence.
    """

    warnings: list[str] = []
    citations, dropped, duplicates = _build_citations(
        diagnosis.citations,
        collector,
    )
    if dropped:
        warnings.append(
            f"{dropped} cited chunk identifier(s) were not returned by the "
            "knowledge tool and were removed."
        )
    if duplicates:
        warnings.append(
            f"{duplicates} duplicate citation identifier(s) were removed."
        )

    dropped_evidence = 0
    causes: list[DiagnosticCause] = []
    for cause in diagnosis.probable_causes:
        evidence_ids, cause_dropped = _validate_evidence_ids(
            cause.evidence_chunk_ids,
            collector,
        )
        dropped_evidence += cause_dropped
        causes.append(
            DiagnosticCause(
                cause=cause.cause,
                basis=cause.basis,
                evidence_chunk_ids=evidence_ids,
            )
        )

    checks: list[DiagnosticCheck] = []
    for check in diagnosis.recommended_checks:
        evidence_ids, check_dropped = _validate_evidence_ids(
            check.evidence_chunk_ids,
            collector,
        )
        dropped_evidence += check_dropped
        checks.append(
            DiagnosticCheck(
                step=check.step,
                safety_note=check.safety_note,
                evidence_chunk_ids=evidence_ids,
            )
        )

    if dropped_evidence:
        warnings.append(
            f"{dropped_evidence} evidence reference(s) were not returned by the "
            "knowledge tool and were removed from causes and checks."
        )

    status = DiagnosticStatus(diagnosis.status)
    if status is DiagnosticStatus.DIAGNOSED and not citations:
        status = DiagnosticStatus.INSUFFICIENT_EVIDENCE
        warnings.append(
            "The proposed diagnosis was not supported by any cited documentation "
            "and was downgraded to insufficient evidence for human review."
        )

    requires_escalation = diagnosis.requires_escalation or status in REVIEW_STATUSES
    escalation_reason = diagnosis.escalation_reason
    if requires_escalation and not escalation_reason:
        escalation_reason = DEFAULT_ESCALATION_REASONS.get(status)

    return DiagnosticResult(
        complaint_id=complaint_id,
        status=status,
        summary=diagnosis.summary,
        probable_causes=tuple(causes),
        recommended_checks=tuple(checks),
        missing_information=_merge_missing_information(
            deterministic_missing_information,
            diagnosis.missing_information,
        ),
        safety_warnings=tuple(diagnosis.safety_warnings),
        conflicting_evidence_notes=tuple(diagnosis.conflicting_evidence_notes),
        requires_escalation=requires_escalation,
        escalation_reason=escalation_reason,
        citations=tuple(citations),
        warnings=tuple(warnings),
    )


def _extract_diagnosis(state: Any) -> ModelDiagnosis:
    if isinstance(state, dict):
        raw = state.get("structured_response")
    else:
        raw = getattr(state, "structured_response", None)

    if isinstance(raw, ModelDiagnosis):
        return raw
    if isinstance(raw, dict):
        try:
            return ModelDiagnosis.model_validate(raw)
        except Exception as exc:
            raise DiagnosticAgentUnavailableError(
                "The diagnostic agent returned an invalid structured response."
            ) from exc
    raise DiagnosticAgentUnavailableError(
        "The diagnostic agent did not return a structured response."
    )


class DiagnosticService:
    """Orchestrate a bounded, read-only technical diagnostic investigation."""

    def __init__(
        self,
        *,
        chat_model_factory: Callable[[], BaseChatModel],
        min_similarity: float,
        knowledge_top_k: int,
        max_service_records: int,
        max_tool_calls: int,
        max_model_calls: int,
        agent_builder: Callable[..., Any] = build_diagnostic_agent,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._chat_model_factory = chat_model_factory
        self._min_similarity = min_similarity
        self._knowledge_top_k = knowledge_top_k
        self._max_service_records = max_service_records
        self._max_tool_calls = max_tool_calls
        self._max_model_calls = max_model_calls
        self._agent_builder = agent_builder
        self._session_factory = session_factory or async_session_factory

    async def investigate(
        self,
        *,
        session: AsyncSession,
        user: User,
        vector_index: VectorIndex,
        complaint_id: uuid.UUID,
        focus: str | None = None,
    ) -> DiagnosticResult:
        if not (is_admin(user) or is_technician(user)):
            raise AccessDeniedError("Complaint not found")

        complaint = await get_complaint_for_operations_user(
            session,
            user,
            complaint_id,
        )

        equipment: Equipment | None = None
        if complaint.equipment_id is not None:
            equipment = await get_equipment_for_customer(
                session,
                complaint.customer_id,
                complaint.equipment_id,
            )

        missing_information = compute_missing_information(complaint, equipment)
        normalized_focus = (focus or "").strip()[:2000] or None
        collector = DiagnosticCollector()
        context = DiagnosticContext(
            session_factory=self._session_factory,
            user=user,
            vector_index=vector_index,
            complaint=complaint,
            equipment=equipment,
            missing_information=missing_information,
            collector=collector,
            knowledge_top_k=self._knowledge_top_k,
            min_similarity=self._min_similarity,
            max_service_records=self._max_service_records,
        )

        try:
            chat_model = self._chat_model_factory()
        except ChatModelConfigurationError as exc:
            raise DiagnosticAgentUnavailableError(
                "The diagnostic model is not configured."
            ) from exc

        agent = self._agent_builder(
            chat_model=chat_model,
            tools=build_diagnostic_tools(),
            max_tool_calls=self._max_tool_calls,
            max_model_calls=self._max_model_calls,
        )
        messages = build_investigation_message(
            complaint,
            equipment,
            missing_information,
            normalized_focus,
        )

        try:
            state = await agent.ainvoke({"messages": messages}, context=context)
        except Exception as exc:
            if context.retrieval_error is not None:
                logger.warning(
                    "Diagnostic knowledge retrieval failed",
                    extra={
                        "event": "diagnostic_retrieval_unavailable",
                        "error_type": type(context.retrieval_error).__name__,
                    },
                )
                raise DiagnosticRetrievalUnavailableError(
                    "Knowledge base search is unavailable."
                ) from exc
            logger.warning(
                "Diagnostic agent invocation failed",
                extra={
                    "event": "diagnostic_agent_failed",
                    "error_type": type(exc).__name__,
                },
            )
            raise DiagnosticAgentUnavailableError(
                "The diagnostic agent could not complete the investigation."
            ) from exc

        if context.retrieval_error is not None:
            logger.warning(
                "Diagnostic knowledge retrieval failed",
                extra={
                    "event": "diagnostic_retrieval_unavailable",
                    "error_type": type(context.retrieval_error).__name__,
                },
            )
            raise DiagnosticRetrievalUnavailableError(
                "Knowledge base search is unavailable."
            )

        diagnosis = _extract_diagnosis(state)
        if not diagnosis.summary.strip():
            raise DiagnosticAgentUnavailableError(
                "The diagnostic agent returned an empty summary."
            )

        return finalize_diagnosis(
            diagnosis,
            complaint_id=complaint.id,
            collector=collector,
            deterministic_missing_information=missing_information,
        )
