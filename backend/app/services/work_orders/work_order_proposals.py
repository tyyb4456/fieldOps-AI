from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint
from app.models.enums import (
    Priority,
    WorkOrderProposalStatus,
    WorkOrderStatus,
)
from app.models.equipment import Equipment
from app.models.user import User
from app.models.work_order import WorkOrder
from app.models.work_order_proposal import WorkOrderProposal
from app.schemas.work_orders.work_order import WorkOrderCreate
from app.services.agents.chat_model import ChatModelConfigurationError
from app.services.agents.work_order_preparation_agent import (
    ModelWorkOrderDraft,
    PreparationContext,
    _citation_snapshot,
    build_preparation_message,
    build_work_order_preparation_agent,
    build_work_order_preparation_tools,
    complaint_context_fingerprint,
    complaint_context_snapshot,
    diagnostic_snapshot,
    extract_draft,
    merge_string_lists,
    normalize_string_list,
    required_skill_list,
)
from app.services.assignments import assignments as assignment_service
from app.services.assignments.technician_recommendation import (
    evaluate_technician,
    recommend_technicians,
    recommendation_ids,
    recommendation_snapshot,
    required_skills_for_equipment,
)
from app.services.diagnostics.diagnostics import (
    DiagnosticService,
    get_complaint_for_operations_user,
)
from app.services.equipment.equipment import get_equipment_for_customer
from app.services.rag.vector_index import VectorIndex
from app.services.shared.authorization import (
    AccessDeniedError,
    require_admin,
)
from app.services.work_orders import work_orders as work_order_service

logger = logging.getLogger(__name__)

PENDING_PROPOSAL_INDEX_NAME = "uq_work_order_proposals_pending_complaint"

COMPLAINT_STATUSES_ELIGIBLE_FOR_PROPOSAL = (
    work_order_service.COMPLAINT_STATUSES_ELIGIBLE_FOR_CONVERSION
)

MAX_PROPOSAL_TEXT_LENGTH = 10000
MAX_ESTIMATED_DURATION_MINUTES = 7 * 24 * 60


class WorkOrderProposalError(Exception):
    """Base class for proposal lifecycle failures."""


class ProposalNotEligibleError(WorkOrderProposalError):
    """The complaint cannot currently be prepared for conversion."""


class ProposalAlreadyPendingError(WorkOrderProposalError):
    """A pending proposal already exists for the complaint."""


class ProposalAlreadyConvertedError(WorkOrderProposalError):
    """The complaint already has a work order."""


class InvalidProposalStateError(WorkOrderProposalError):
    """The proposal lifecycle transition is not permitted."""


class ProposalTechnicianNotEligibleError(WorkOrderProposalError):
    """The selected technician cannot be assigned from this proposal."""


class ProposalStaleError(WorkOrderProposalError):
    """The complaint context changed after the proposal was generated."""


class ProposalAgentUnavailableError(WorkOrderProposalError):
    """The preparation model or agent could not draft a proposal."""


class ProposalGenerationError(WorkOrderProposalError):
    """The agent returned a proposal that failed validation."""


def is_pending_proposal_conflict(exc: IntegrityError) -> bool:
    original = exc.orig
    constraint_name = getattr(original, "constraint_name", None)
    if constraint_name == PENDING_PROPOSAL_INDEX_NAME:
        return True
    diagnostics = getattr(original, "diag", None)
    if (
        getattr(diagnostics, "constraint_name", None)
        == PENDING_PROPOSAL_INDEX_NAME
    ):
        return True
    return PENDING_PROPOSAL_INDEX_NAME in str(original)


def _required_text(
    value: str,
    *,
    field: str,
    max_length: int,
) -> str:
    text = value.strip()
    if not text:
        raise ProposalGenerationError(f"The proposal {field} is empty.")
    if len(text) > max_length:
        raise ProposalGenerationError(
            f"The proposal {field} is too long."
        )
    return text


def finalize_draft(
    draft: ModelWorkOrderDraft,
    *,
    diagnosis: Any,
    required_skills: tuple[str, ...],
    recommendation_warnings: tuple[str, ...],
) -> dict[str, Any]:
    """Validate the model draft and merge backend-owned facts.

    The model contributes prose and suggestions. Skills, citations,
    escalation and technician data remain application-owned.
    """

    try:
        priority = Priority(draft.priority)
    except ValueError as exc:
        raise ProposalGenerationError(
            "The proposal priority is not a supported value."
        ) from exc

    estimated_duration = draft.estimated_duration_minutes
    if estimated_duration is not None and not (
        0 <= estimated_duration <= MAX_ESTIMATED_DURATION_MINUTES
    ):
        raise ProposalGenerationError(
            "The proposal duration estimate is outside the permitted range."
        )

    missing_information = merge_string_lists(
        list(diagnosis.missing_information),
        normalize_string_list(draft.missing_information),
    )
    safety_warnings = merge_string_lists(
        list(diagnosis.safety_warnings),
        normalize_string_list(draft.safety_warnings),
    )

    warnings = merge_string_lists(
        [
            (
                "This work-order proposal was generated by an AI agent and "
                "requires human review before any work is authorized."
            ),
            (
                "Technician recommendations are based on stored profile data; "
                "specific availability is not confirmed by any calendar."
            ),
            (
                "Required parts and the duration estimate are unverified "
                "suggestions and must be confirmed before dispatch."
            ),
        ],
        list(diagnosis.warnings),
        list(recommendation_warnings),
    )

    return {
        "title": _required_text(
            draft.title,
            field="title",
            max_length=255,
        ),
        "problem_description": _required_text(
            draft.problem_description,
            field="problem description",
            max_length=MAX_PROPOSAL_TEXT_LENGTH,
        ),
        "proposed_scope": _required_text(
            draft.proposed_scope,
            field="scope",
            max_length=MAX_PROPOSAL_TEXT_LENGTH,
        ),
        "technical_findings": _required_text(
            draft.technical_findings,
            field="technical findings",
            max_length=MAX_PROPOSAL_TEXT_LENGTH,
        ),
        "recommended_actions": normalize_string_list(
            draft.recommended_actions
        ),
        "required_skills": required_skill_list(required_skills),
        "required_parts": normalize_string_list(draft.required_parts),
        "priority": priority,
        "estimated_duration_minutes": estimated_duration,
        "safety_warnings": safety_warnings,
        "missing_information": missing_information,
        "generation_warnings": warnings,
    }


def _checklist_from_snapshot(snapshot: Any) -> list[Any]:
    if not isinstance(snapshot, dict):
        return []
    raw = snapshot.get("diagnostic_checklist")
    if not isinstance(raw, list):
        return []
    checklist: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        step = item.get("step")
        if not isinstance(step, str) or not step.strip():
            continue
        entry = {"step": step.strip()}
        safety_note = item.get("safety_note")
        if isinstance(safety_note, str) and safety_note.strip():
            entry["safety_note"] = safety_note.strip()
        checklist.append(entry)
    return checklist


async def _lock_proposal(
    session: AsyncSession,
    proposal_id: uuid.UUID,
) -> WorkOrderProposal:
    result = await session.execute(
        select(WorkOrderProposal)
        .where(WorkOrderProposal.id == proposal_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise AccessDeniedError("Work order proposal not found")
    return proposal


async def _lock_complaint(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> Complaint:
    result = await session.execute(
        select(Complaint)
        .where(Complaint.id == complaint_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    complaint = result.scalar_one_or_none()
    if complaint is None:
        raise AccessDeniedError("Complaint not found")
    return complaint


async def _load_current_equipment(
    session: AsyncSession,
    complaint: Complaint,
) -> Equipment:
    result = await session.execute(
        select(Equipment)
        .where(
            Equipment.id == complaint.equipment_id,
            Equipment.customer_id == complaint.customer_id,
        )
        .execution_options(populate_existing=True)
    )
    equipment = result.scalar_one_or_none()
    if equipment is None:
        raise AccessDeniedError("Equipment not found")
    return equipment


def _ensure_context_current(
    stored_fingerprint: Any,
    complaint: Complaint,
    equipment: Equipment,
) -> None:
    current = complaint_context_fingerprint(complaint, equipment)
    if (
        not isinstance(stored_fingerprint, str)
        or stored_fingerprint != current
    ):
        raise ProposalStaleError(
            "The complaint context changed after this proposal was prepared. "
            "Generate a new proposal before approval."
        )


def _ensure_proposal_context_current(
    proposal: WorkOrderProposal,
    complaint: Complaint,
    equipment: Equipment,
) -> None:
    """Reject a proposal whose proposal-relevant context has changed.

    The stored fingerprint is produced only from operationally significant
    fields (see ``complaint_context_fingerprint``). Unrelated metadata updates
    do not change the fingerprint. A missing fingerprint is treated as stale
    because the proposal cannot be proven current.
    """

    snapshot = proposal.context_snapshot
    stored = (
        snapshot.get("context_fingerprint")
        if isinstance(snapshot, dict)
        else None
    )
    _ensure_context_current(stored, complaint, equipment)


async def get_proposal(
    session: AsyncSession,
    user: User,
    proposal_id: uuid.UUID,
) -> WorkOrderProposal:
    require_admin(user)
    proposal = await session.get(WorkOrderProposal, proposal_id)
    if proposal is None:
        raise AccessDeniedError("Work order proposal not found")
    return proposal


async def list_proposals(
    session: AsyncSession,
    user: User,
    *,
    status: WorkOrderProposalStatus | None,
    complaint_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[WorkOrderProposal], int]:
    require_admin(user)
    filters = []
    if status is not None:
        filters.append(WorkOrderProposal.status == status)
    if complaint_id is not None:
        filters.append(WorkOrderProposal.complaint_id == complaint_id)

    scoped = select(WorkOrderProposal).where(*filters)
    total = await session.scalar(
        select(func.count()).select_from(scoped.subquery())
    )
    result = await session.execute(
        scoped.order_by(
            WorkOrderProposal.created_at.desc(),
            WorkOrderProposal.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


class WorkOrderProposalService:
    """Orchestrate proposal generation, human review and approved execution."""

    def __init__(
        self,
        *,
        diagnostic_service: DiagnosticService,
        chat_model_factory: Callable[[], BaseChatModel],
        max_tool_calls: int,
        max_model_calls: int,
        technician_limit: int,
        agent_builder: Callable[..., Any] = build_work_order_preparation_agent,
    ) -> None:
        self._diagnostic_service = diagnostic_service
        self._chat_model_factory = chat_model_factory
        self._max_tool_calls = max_tool_calls
        self._max_model_calls = max_model_calls
        self._technician_limit = technician_limit
        self._agent_builder = agent_builder

    async def get(
        self,
        session: AsyncSession,
        user: User,
        proposal_id: uuid.UUID,
    ) -> WorkOrderProposal:
        return await get_proposal(session, user, proposal_id)

    async def list_proposals(
        self,
        session: AsyncSession,
        user: User,
        *,
        status: WorkOrderProposalStatus | None,
        complaint_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[WorkOrderProposal], int]:
        return await list_proposals(
            session,
            user,
            status=status,
            complaint_id=complaint_id,
            limit=limit,
            offset=offset,
        )

    async def generate(
        self,
        *,
        session: AsyncSession,
        user: User,
        vector_index: VectorIndex,
        complaint_id: uuid.UUID,
    ) -> WorkOrderProposal:
        # Phase A: all reads, retrieval, model calls and deterministic ranking
        # happen with plain SELECTs only. No complaint row lock and no write is
        # issued here, so no lock is held while waiting on the diagnostic or
        # preparation provider.
        complaint = await get_complaint_for_operations_user(
            session,
            user,
            complaint_id,
        )
        await session.refresh(complaint)

        if complaint.status not in COMPLAINT_STATUSES_ELIGIBLE_FOR_PROPOSAL:
            raise ProposalNotEligibleError(
                "Complaint is not eligible for work-order preparation."
            )
        if complaint.equipment_id is None:
            raise ProposalNotEligibleError(
                "Complaint has no identified equipment."
            )

        existing_work_order = await session.scalar(
            select(WorkOrder.id).where(
                WorkOrder.complaint_id == complaint.id
            )
        )
        if existing_work_order is not None:
            raise ProposalAlreadyConvertedError(
                "A work order already exists for this complaint."
            )

        pending = await session.scalar(
            select(WorkOrderProposal.id).where(
                WorkOrderProposal.complaint_id == complaint.id,
                WorkOrderProposal.status
                == WorkOrderProposalStatus.PENDING_APPROVAL,
            )
        )
        if pending is not None:
            raise ProposalAlreadyPendingError(
                "A work order proposal is already pending review."
            )

        equipment = await get_equipment_for_customer(
            session,
            complaint.customer_id,
            complaint.equipment_id,
        )
        await session.refresh(equipment)

        diagnosis = await self._diagnostic_service.investigate(
            session=session,
            user=user,
            vector_index=vector_index,
            complaint_id=complaint.id,
        )

        required_skills = required_skills_for_equipment(equipment)
        technician_result = await recommend_technicians(
            session,
            required_skills=required_skills,
            limit=self._technician_limit,
        )

        try:
            chat_model = self._chat_model_factory()
        except ChatModelConfigurationError as exc:
            raise ProposalAgentUnavailableError(
                "The proposal model is not configured."
            ) from exc

        agent = self._agent_builder(
            chat_model=chat_model,
            tools=build_work_order_preparation_tools(),
            max_tool_calls=self._max_tool_calls,
            max_model_calls=self._max_model_calls,
        )
        context = PreparationContext(
            complaint=complaint,
            equipment=equipment,
            diagnosis=diagnosis,
            required_skills=required_skills,
        )
        messages = build_preparation_message(
            complaint=complaint,
            equipment=equipment,
            diagnosis=diagnosis,
            required_skills=required_skills,
        )

        try:
            state = await agent.ainvoke(
                {"messages": messages},
                context=context,
            )
        except Exception as exc:
            logger.warning(
                "Work-order preparation agent invocation failed",
                extra={
                    "event": "work_order_preparation_agent_failed",
                    "error_type": type(exc).__name__,
                },
            )
            raise ProposalAgentUnavailableError(
                "The work-order preparation agent could not complete the draft."
            ) from exc

        try:
            draft = extract_draft(state)
        except ValueError as exc:
            raise ProposalAgentUnavailableError(
                "The work-order preparation agent returned an invalid response."
            ) from exc

        finalized = finalize_draft(
            draft,
            diagnosis=diagnosis,
            required_skills=required_skills,
            recommendation_warnings=technician_result.warnings,
        )
        snapshot = complaint_context_snapshot(
            complaint=complaint,
            equipment=equipment,
            diagnosis=diagnosis,
            required_skills=required_skills,
            technician_result=technician_result,
        )

        # Phase B: acquire the complaint row lock, revalidate against current
        # database state and persist the proposal in one short transaction.
        return await self._persist_proposal(
            session=session,
            user=user,
            complaint_id=complaint.id,
            finalized=finalized,
            diagnosis=diagnosis,
            snapshot=snapshot,
            technician_result=technician_result,
        )

    async def _persist_proposal(
        self,
        *,
        session: AsyncSession,
        user: User,
        complaint_id: uuid.UUID,
        finalized: dict[str, Any],
        diagnosis: Any,
        snapshot: dict[str, Any],
        technician_result: Any,
    ) -> WorkOrderProposal:
        await get_complaint_for_operations_user(
            session,
            user,
            complaint_id,
        )
        complaint = await _lock_complaint(session, complaint_id)

        if complaint.status not in COMPLAINT_STATUSES_ELIGIBLE_FOR_PROPOSAL:
            raise ProposalNotEligibleError(
                "Complaint is no longer eligible for work-order preparation."
            )
        if complaint.equipment_id is None:
            raise ProposalNotEligibleError(
                "Complaint has no identified equipment."
            )

        equipment = await _load_current_equipment(session, complaint)
        _ensure_context_current(
            snapshot.get("context_fingerprint"),
            complaint,
            equipment,
        )

        existing_work_order = await session.scalar(
            select(WorkOrder.id).where(
                WorkOrder.complaint_id == complaint.id
            )
        )
        if existing_work_order is not None:
            raise ProposalAlreadyConvertedError(
                "A work order already exists for this complaint."
            )

        pending = await session.scalar(
            select(WorkOrderProposal.id).where(
                WorkOrderProposal.complaint_id == complaint.id,
                WorkOrderProposal.status
                == WorkOrderProposalStatus.PENDING_APPROVAL,
            )
        )
        if pending is not None:
            raise ProposalAlreadyPendingError(
                "A work order proposal is already pending review."
            )

        proposal = WorkOrderProposal(
            complaint_id=complaint.id,
            status=WorkOrderProposalStatus.PENDING_APPROVAL,
            context_snapshot=snapshot,
            title=finalized["title"],
            problem_description=finalized["problem_description"],
            proposed_scope=finalized["proposed_scope"],
            technical_findings=finalized["technical_findings"],
            recommended_actions=finalized["recommended_actions"],
            required_skills=finalized["required_skills"],
            required_parts=finalized["required_parts"],
            priority=finalized["priority"],
            estimated_duration_minutes=finalized[
                "estimated_duration_minutes"
            ],
            safety_warnings=finalized["safety_warnings"],
            missing_information=finalized["missing_information"],
            generation_warnings=finalized["generation_warnings"],
            diagnostic_status=diagnosis.status.value,
            diagnostic_summary=diagnosis.summary,
            diagnostic_snapshot=diagnostic_snapshot(diagnosis),
            citations=_citation_snapshot(diagnosis),
            requires_escalation=diagnosis.requires_escalation,
            escalation_reason=diagnosis.escalation_reason,
            technician_recommendations=recommendation_snapshot(
                technician_result
            ),
            created_by_id=user.id,
        )
        session.add(proposal)
        await session.flush()
        return proposal

    async def approve(
        self,
        *,
        session: AsyncSession,
        admin: User,
        proposal_id: uuid.UUID,
        technician_id: uuid.UUID | None,
    ) -> WorkOrderProposal:
        require_admin(admin)
        proposal = await _lock_proposal(session, proposal_id)

        if proposal.status is not WorkOrderProposalStatus.PENDING_APPROVAL:
            raise InvalidProposalStateError(
                "Only a pending proposal can be approved."
            )

        complaint = await _lock_complaint(session, proposal.complaint_id)
        if complaint.status not in COMPLAINT_STATUSES_ELIGIBLE_FOR_PROPOSAL:
            raise InvalidProposalStateError(
                "The complaint is no longer eligible for work-order conversion."
            )
        if complaint.equipment_id is None:
            raise InvalidProposalStateError(
                "The complaint no longer has identified equipment."
            )

        equipment = await _load_current_equipment(session, complaint)
        _ensure_proposal_context_current(proposal, complaint, equipment)

        existing_work_order = await session.scalar(
            select(WorkOrder.id).where(
                WorkOrder.complaint_id == complaint.id
            )
        )
        if existing_work_order is not None:
            raise InvalidProposalStateError(
                "A work order already exists for this complaint."
            )

        required_skills = tuple(
            normalize_string_list(list(proposal.required_skills))
        )
        if technician_id is not None:
            await self._validate_selected_technician(
                session,
                proposal=proposal,
                complaint=complaint,
                technician_id=technician_id,
                required_skills=required_skills,
            )

        try:
            work_order = (
                await work_order_service.create_work_order_from_complaint(
                    session,
                    complaint_id=complaint.id,
                    data=WorkOrderCreate(
                        title=proposal.title,
                        description=proposal.problem_description,
                        diagnostic_checklist=_checklist_from_snapshot(
                            proposal.diagnostic_snapshot
                        ),
                        priority=proposal.priority,
                    ),
                    actor_id=admin.id,
                )
            )
        except work_order_service.WorkOrderAlreadyExistsError as exc:
            raise InvalidProposalStateError(
                "A work order already exists for this complaint."
            ) from exc
        except work_order_service.InvalidComplaintConversionError as exc:
            raise InvalidProposalStateError(
                "The complaint is no longer eligible for conversion."
            ) from exc

        assignment = None
        if technician_id is not None:
            await work_order_service.transition_work_order(
                session,
                user=admin,
                work_order_id=work_order.id,
                target_status=WorkOrderStatus.VALIDATED,
            )
            await work_order_service.transition_work_order(
                session,
                user=admin,
                work_order_id=work_order.id,
                target_status=WorkOrderStatus.AWAITING_ASSIGNMENT,
            )
            try:
                assignment = await assignment_service.create_assignment(
                    session,
                    work_order_id=work_order.id,
                    technician_id=technician_id,
                )
            except assignment_service.TechnicianNotEligibleError as exc:
                raise ProposalTechnicianNotEligibleError(
                    "The selected technician is no longer eligible."
                ) from exc

        now = datetime.now(UTC)
        proposal.status = WorkOrderProposalStatus.APPROVED
        proposal.reviewed_by_id = admin.id
        proposal.reviewed_at = now
        proposal.rejection_reason = None
        proposal.selected_technician_id = technician_id
        proposal.resulting_work_order_id = work_order.id
        proposal.resulting_assignment_id = (
            assignment.id if assignment is not None else None
        )
        await session.flush()
        return proposal

    async def _validate_selected_technician(
        self,
        session: AsyncSession,
        *,
        proposal: WorkOrderProposal,
        complaint: Complaint,
        technician_id: uuid.UUID,
        required_skills: tuple[str, ...],
    ) -> None:
        stored = recommendation_ids(proposal.technician_recommendations)
        stored_entry = stored.get(technician_id)
        if stored_entry is None:
            raise ProposalTechnicianNotEligibleError(
                "The selected technician is not part of this proposal's "
                "recommendations."
            )
        if stored_entry.get("eligible") is not True:
            raise ProposalTechnicianNotEligibleError(
                "The selected technician was not eligible when the proposal "
                "was generated."
            )

        evaluation = await evaluate_technician(
            session,
            technician_id=technician_id,
            required_skills=required_skills,
        )
        if evaluation is None or not evaluation.eligible:
            raise ProposalTechnicianNotEligibleError(
                "The selected technician is no longer eligible for assignment."
            )

        snapshot = proposal.context_snapshot
        if isinstance(snapshot, dict):
            equipment = snapshot.get("equipment")
            if isinstance(equipment, dict):
                snapshot_equipment_id = equipment.get("id")
                if (
                    snapshot_equipment_id is not None
                    and str(snapshot_equipment_id)
                    != str(complaint.equipment_id)
                ):
                    raise InvalidProposalStateError(
                        "The complaint equipment changed after the proposal was "
                        "generated; regenerate the proposal before approval."
                    )

    async def reject(
        self,
        *,
        session: AsyncSession,
        admin: User,
        proposal_id: uuid.UUID,
        reason: str,
    ) -> WorkOrderProposal:
        require_admin(admin)
        proposal = await _lock_proposal(session, proposal_id)

        if proposal.status is not WorkOrderProposalStatus.PENDING_APPROVAL:
            raise InvalidProposalStateError(
                "Only a pending proposal can be rejected."
            )

        proposal.status = WorkOrderProposalStatus.REJECTED
        proposal.reviewed_by_id = admin.id
        proposal.reviewed_at = datetime.now(UTC)
        proposal.rejection_reason = reason.strip()
        await session.flush()
        return proposal


def log_proposal_event(
    event: str,
    *,
    actor_id: uuid.UUID,
    proposal: WorkOrderProposal,
) -> None:
    logger.info(
        "Work-order proposal lifecycle event",
        extra={
            "event": event,
            "actor_id": str(actor_id),
            "proposal_id": str(proposal.id),
            "complaint_id": str(proposal.complaint_id),
            "status": proposal.status.value,
            "resulting_work_order_id": (
                str(proposal.resulting_work_order_id)
                if proposal.resulting_work_order_id is not None
                else None
            ),
            "resulting_assignment_id": (
                str(proposal.resulting_assignment_id)
                if proposal.resulting_assignment_id is not None
                else None
            ),
        },
    )


__all__ = [
    "InvalidProposalStateError",
    "ProposalAgentUnavailableError",
    "ProposalAlreadyConvertedError",
    "ProposalAlreadyPendingError",
    "ProposalGenerationError",
    "ProposalNotEligibleError",
    "ProposalStaleError",
    "ProposalTechnicianNotEligibleError",
    "WorkOrderProposalError",
    "WorkOrderProposalService",
    "is_pending_proposal_conflict",
]
