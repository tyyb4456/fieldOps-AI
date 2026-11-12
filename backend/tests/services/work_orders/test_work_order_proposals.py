from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies.work_order_proposals import (
    get_work_order_proposal_service,
)
from app.main import app
from app.models.complaint import Complaint
from app.models.enums import (
    AssignmentStatus,
    ComplaintChannel,
    ComplaintStatus,
    Priority,
    WorkOrderProposalStatus,
    WorkOrderStatus,
)
from app.models.equipment import Equipment
from app.models.technician_assignment import TechnicianAssignment
from app.models.work_order import WorkOrder
from app.models.work_order_proposal import WorkOrderProposal
from app.schemas.diagnostics.diagnostic import DiagnosticStatus
from app.services.agents.work_order_preparation_agent import (
    ModelWorkOrderDraft,
    PreparationContext,
    build_preparation_message,
    build_work_order_preparation_agent,
    build_work_order_preparation_tools,
)
from app.services.assignments import assignments as assignment_service
from app.services.assignments.technician_recommendation import recommend_technicians
from app.services.diagnostics.diagnostics import (
    DiagnosticCheck,
    DiagnosticResult,
    DiagnosticService,
)
from app.services.rag.knowledge_answer import Citation
from app.services.work_orders.work_order_proposals import (
    ProposalAlreadyPendingError,
    ProposalNotEligibleError,
    ProposalStaleError,
    ProposalTechnicianNotEligibleError,
    WorkOrderProposalService,
)
from tests.support import (
    bearer,
    seed_admin,
    seed_complaint,
    seed_customer,
    seed_equipment,
    seed_technician,
)


class StubDiagnosticService:
    def __init__(self, result: DiagnosticResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def investigate(self, **kwargs: Any) -> DiagnosticResult:
        self.calls.append(kwargs)
        return self.result


class StubPreparationAgent:
    def __init__(self, draft: ModelWorkOrderDraft) -> None:
        self.draft = draft

    async def ainvoke(
        self,
        payload: dict[str, Any],
        *,
        context: Any,
    ) -> dict[str, Any]:
        return {
            "messages": payload["messages"],
            "structured_response": self.draft,
        }


def _agent_builder(draft: ModelWorkOrderDraft):
    def build(**kwargs: Any) -> StubPreparationAgent:
        return StubPreparationAgent(draft)

    return build


def _diagnosis(complaint_id: uuid.UUID) -> DiagnosticResult:
    return DiagnosticResult(
        complaint_id=complaint_id,
        status=DiagnosticStatus.DIAGNOSED,
        summary="The manual supports checking the DC input before replacement.",
        probable_causes=(),
        recommended_checks=(
            DiagnosticCheck(
                step="De-energize and inspect the DC input fuse.",
                safety_note="De-energize the inverter before inspection.",
                evidence_chunk_ids=(),
            ),
        ),
        missing_information=(),
        safety_warnings=("De-energize the inverter before inspection.",),
        conflicting_evidence_notes=(),
        requires_escalation=False,
        escalation_reason=None,
        citations=(
            Citation(
                source_id="S1",
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_name="Acme Solar INV-5000 Manual",
                manufacturer="Acme Solar",
                model="INV-5000",
                version="1.0",
                page_number=12,
                chunk_index=3,
                excerpt="Check the DC input fuse before replacement.",
            ),
        ),
        warnings=(),
    )


def _draft() -> ModelWorkOrderDraft:
    return ModelWorkOrderDraft(
        title="Replace DC input fuse",
        problem_description="The inverter reports a DC input fault and is not generating.",
        proposed_scope="Inspect the DC input and replace the fuse if documented.",
        technical_findings=(
            "The approved manual documents a DC input fault. On-site verification "
            "is still required."
        ),
        recommended_actions=["De-energize the inverter", "Inspect the DC input fuse"],
        required_parts=["DC input fuse (verify part number on site)"],
        priority="high",
        estimated_duration_minutes=90,
        safety_warnings=["Confirm isolation before opening the enclosure."],
        missing_information=["measured DC input voltage"],
    )


def _service(
    diagnosis: DiagnosticResult,
    *,
    draft: ModelWorkOrderDraft | None = None,
) -> WorkOrderProposalService:
    return WorkOrderProposalService(
        diagnostic_service=cast(
            DiagnosticService,
            StubDiagnosticService(diagnosis),
        ),
        chat_model_factory=lambda: cast(Any, object()),
        max_tool_calls=3,
        max_model_calls=3,
        technician_limit=100,
        agent_builder=_agent_builder(draft or _draft()),
    )


async def _seed_ready_complaint(
    session: AsyncSession,
) -> tuple[Any, Any, Any]:
    _, customer, _ = await seed_customer(session)
    equipment = await seed_equipment(session, customer)
    complaint = await seed_complaint(
        session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    return customer, equipment, complaint


async def _seed_skilled_technician(
    session: AsyncSession,
    *,
    full_name: str = "Skilled Tech",
    skills: dict[str, Any] | None = None,
    is_available: bool = True,
):
    _, technician, token = await seed_technician(
        session,
        full_name=full_name,
    )
    technician.skills = skills or {"equipment_types": ["solar_inverter"]}
    technician.is_available = is_available
    await session.commit()
    return technician, token


@pytest.mark.asyncio
async def test_recommend_technicians_ranks_eligible_profiles_deterministically(
    db_session: AsyncSession,
) -> None:
    skilled, _ = await _seed_skilled_technician(
        db_session,
        full_name="Alice Skilled",
    )
    unskilled, _ = await _seed_skilled_technician(
        db_session,
        full_name="Bob General",
        skills={},
    )
    unavailable, _ = await _seed_skilled_technician(
        db_session,
        full_name="Carol Offline",
        is_available=False,
    )

    result = await recommend_technicians(
        db_session,
        required_skills=("solar_inverter",),
        limit=10,
    )
    repeated = await recommend_technicians(
        db_session,
        required_skills=("solar_inverter",),
        limit=10,
    )

    assert [item.technician_id for item in result.recommendations] == [
        item.technician_id for item in repeated.recommendations
    ]
    assert result.recommendations[0].technician_id == skilled.id
    assert result.recommendations[0].eligible is True
    assert result.recommendations[1].technician_id == unskilled.id
    assert result.recommendations[1].eligible is True

    excluded = next(
        item
        for item in result.recommendations
        if item.technician_id == unavailable.id
    )
    assert excluded.eligible is False
    assert any("unavailable" in reason.casefold() for reason in excluded.reasons)
    assert all(
        item.availability_status == "unknown"
        for item in result.recommendations
        if item.eligible
    )
    assert any("calendar" in warning.casefold() for warning in result.warnings)


@pytest.mark.asyncio
async def test_generate_persists_pending_proposal_without_business_mutation(
    db_session: AsyncSession,
) -> None:
    admin, _ = await seed_admin(db_session)
    technician, _ = await _seed_skilled_technician(db_session)
    _, _, complaint = await _seed_ready_complaint(db_session)
    service = _service(_diagnosis(complaint.id))

    proposal = await service.generate(
        session=db_session,
        user=admin,
        vector_index=cast(Any, None),
        complaint_id=complaint.id,
    )
    await db_session.commit()

    assert proposal.status.value == "pending_approval"
    assert proposal.created_by_id == admin.id
    assert proposal.required_skills == ["solar_inverter"]
    assert proposal.priority.value == "high"
    assert proposal.requires_escalation is False
    assert len(proposal.citations) == 1
    assert proposal.citations[0]["document_name"] == "Acme Solar INV-5000 Manual"
    assert any(
        item["technician_id"] == str(technician.id)
        for item in proposal.technician_recommendations
    )
    assert proposal.resulting_work_order_id is None
    assert proposal.resulting_assignment_id is None

    work_order_count = await db_session.scalar(
        select(func.count(WorkOrder.id)).where(
            WorkOrder.complaint_id == complaint.id
        )
    )
    assignment_count = await db_session.scalar(
        select(func.count(TechnicianAssignment.id))
    )
    assert work_order_count == 0
    assert assignment_count == 0


@pytest.mark.asyncio
async def test_second_pending_proposal_is_rejected(
    db_session: AsyncSession,
) -> None:
    admin, _ = await seed_admin(db_session)
    await _seed_skilled_technician(db_session)
    _, _, complaint = await _seed_ready_complaint(db_session)
    service = _service(_diagnosis(complaint.id))

    await service.generate(
        session=db_session,
        user=admin,
        vector_index=cast(Any, None),
        complaint_id=complaint.id,
    )
    await db_session.commit()

    with pytest.raises(ProposalAlreadyPendingError):
        await service.generate(
            session=db_session,
            user=admin,
            vector_index=cast(Any, None),
            complaint_id=complaint.id,
        )


@pytest.mark.asyncio
async def test_generation_requires_eligible_complaint(
    db_session: AsyncSession,
) -> None:
    admin, _ = await seed_admin(db_session)
    _, customer, _ = await seed_customer(db_session)
    equipment = await seed_equipment(db_session, customer)
    complaint = await seed_complaint(
        db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.RECEIVED,
    )
    service = _service(_diagnosis(complaint.id))

    with pytest.raises(ProposalNotEligibleError):
        await service.generate(
            session=db_session,
            user=admin,
            vector_index=cast(Any, None),
            complaint_id=complaint.id,
        )


@pytest.mark.asyncio
async def test_approval_creates_work_order_and_offered_assignment(
    db_session: AsyncSession,
) -> None:
    admin, _ = await seed_admin(db_session)
    technician, _ = await _seed_skilled_technician(db_session)
    _, _, complaint = await _seed_ready_complaint(db_session)
    service = _service(_diagnosis(complaint.id))

    proposal = await service.generate(
        session=db_session,
        user=admin,
        vector_index=cast(Any, None),
        complaint_id=complaint.id,
    )
    await db_session.commit()

    approved = await service.approve(
        session=db_session,
        admin=admin,
        proposal_id=proposal.id,
        technician_id=technician.id,
    )
    await db_session.commit()

    assert approved.status.value == "approved"
    assert approved.reviewed_by_id == admin.id
    assert approved.reviewed_at is not None
    assert approved.resulting_work_order_id is not None
    assert approved.resulting_assignment_id is not None

    work_order = await db_session.get(
        WorkOrder,
        approved.resulting_work_order_id,
    )
    assignment = await db_session.get(
        TechnicianAssignment,
        approved.resulting_assignment_id,
    )
    refreshed_complaint = await db_session.get(type(complaint), complaint.id)

    assert work_order is not None
    assert work_order.status is WorkOrderStatus.ASSIGNED
    assert work_order.description == proposal.problem_description
    assert assignment is not None
    assert assignment.technician_id == technician.id
    assert assignment.assignment_status is AssignmentStatus.OFFERED
    assert refreshed_complaint is not None
    assert refreshed_complaint.status is ComplaintStatus.CONVERTED


@pytest.mark.asyncio
async def test_approval_revalidates_technician_eligibility(
    db_session: AsyncSession,
) -> None:
    admin, _ = await seed_admin(db_session)
    technician, _ = await _seed_skilled_technician(db_session)
    _, _, complaint = await _seed_ready_complaint(db_session)
    complaint_id = complaint.id
    service = _service(_diagnosis(complaint.id))

    proposal = await service.generate(
        session=db_session,
        user=admin,
        vector_index=cast(Any, None),
        complaint_id=complaint_id,
    )
    await db_session.commit()
    proposal_id = proposal.id

    technician.is_available = False
    await db_session.commit()

    with pytest.raises(ProposalTechnicianNotEligibleError):
        await service.approve(
            session=db_session,
            admin=admin,
            proposal_id=proposal_id,
            technician_id=technician.id,
        )
    await db_session.rollback()

    proposal_count = await db_session.scalar(
        select(func.count(WorkOrderProposal.id)).where(
            WorkOrderProposal.id == proposal_id
        )
    )
    work_order_count = await db_session.scalar(
        select(func.count(WorkOrder.id)).where(
            WorkOrder.complaint_id == complaint_id
        )
    )
    assert proposal_count == 1
    assert work_order_count == 0


@pytest.mark.asyncio
async def test_rejection_records_reason_and_allows_regeneration(
    db_session: AsyncSession,
) -> None:
    admin, _ = await seed_admin(db_session)
    await _seed_skilled_technician(db_session)
    _, _, complaint = await _seed_ready_complaint(db_session)
    service = _service(_diagnosis(complaint.id))

    proposal = await service.generate(
        session=db_session,
        user=admin,
        vector_index=cast(Any, None),
        complaint_id=complaint.id,
    )
    await db_session.commit()

    rejected = await service.reject(
        session=db_session,
        admin=admin,
        proposal_id=proposal.id,
        reason="Insufficient diagnostic evidence; request an on-site inspection.",
    )
    await db_session.commit()

    assert rejected.status.value == "rejected"
    assert rejected.reviewed_at is not None
    assert "on-site" in (rejected.rejection_reason or "")

    regenerated = await service.generate(
        session=db_session,
        user=admin,
        vector_index=cast(Any, None),
        complaint_id=complaint.id,
    )
    await db_session.commit()
    assert regenerated.id != proposal.id
    assert regenerated.status.value == "pending_approval"


@pytest.mark.asyncio
async def test_api_generate_approve_and_role_boundaries(
    migrated_db_session: AsyncSession,
    api_client: Any,
) -> None:
    admin, admin_token = await seed_admin(migrated_db_session)
    technician, technician_token = await _seed_skilled_technician(
        migrated_db_session
    )
    _, _, complaint = await _seed_ready_complaint(migrated_db_session)

    service = _service(_diagnosis(complaint.id))
    app.dependency_overrides[get_work_order_proposal_service] = lambda: service

    generate_response = await api_client.post(
        f"/api/v1/admin/complaints/{complaint.id}/work-order-proposals",
        headers=bearer(admin_token),
    )
    assert generate_response.status_code == 201
    generated = generate_response.json()
    assert generated["status"] == "pending_approval"
    assert generated["created_by_id"] == str(admin.id)
    proposal_id = generated["id"]

    forbidden_approve = await api_client.post(
        f"/api/v1/admin/work-order-proposals/{proposal_id}/approve",
        json={"technician_id": str(technician.id)},
        headers=bearer(technician_token),
    )
    assert forbidden_approve.status_code == 403

    approve_response = await api_client.post(
        f"/api/v1/admin/work-order-proposals/{proposal_id}/approve",
        json={"technician_id": str(technician.id)},
        headers=bearer(admin_token),
    )
    assert approve_response.status_code == 200
    approved = approve_response.json()
    assert approved["status"] == "approved"
    assert approved["resulting_work_order_id"] is not None
    assert approved["resulting_assignment_id"] is not None

    read_response = await api_client.get(
        f"/api/v1/admin/work-order-proposals/{proposal_id}",
        headers=bearer(admin_token),
    )
    assert read_response.status_code == 200

    forbidden_read = await api_client.get(
        f"/api/v1/admin/work-order-proposals/{proposal_id}",
        headers=bearer(technician_token),
    )
    assert forbidden_read.status_code == 403

def _session_factory_for(
    session: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
    assert session.bind is not None
    return async_sessionmaker(
        bind=session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def _assert_complaint_unlocked(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> None:
    """Prove no transaction currently holds a lock on the complaint row."""

    factory = _session_factory_for(session)
    async with factory() as probe:
        try:
            await probe.execute(
                text(
                    "SELECT id FROM complaints WHERE id = :complaint_id "
                    "FOR UPDATE NOWAIT"
                ),
                {"complaint_id": complaint_id},
            )
        except DBAPIError as exc:
            sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(
                exc.orig,
                "pgcode",
                None,
            )
            if sqlstate == "55P03":
                raise AssertionError(
                    "complaint row was locked during a model/retrieval call"
                ) from exc
            raise
        finally:
            await probe.rollback()


class LockProbeDiagnosticService(StubDiagnosticService):
    async def investigate(self, **kwargs: Any) -> DiagnosticResult:
        await _assert_complaint_unlocked(
            kwargs["session"],
            kwargs["complaint_id"],
        )
        return await super().investigate(**kwargs)


class LockProbePreparationAgent(StubPreparationAgent):
    def __init__(
        self,
        draft: ModelWorkOrderDraft,
        session: AsyncSession,
    ) -> None:
        super().__init__(draft)
        self.session = session

    async def ainvoke(
        self,
        payload: dict[str, Any],
        *,
        context: Any,
    ) -> dict[str, Any]:
        await _assert_complaint_unlocked(
            self.session,
            context.complaint.id,
        )
        return await super().ainvoke(payload, context=context)


class ContextMutatingPreparationAgent(StubPreparationAgent):
    def __init__(
        self,
        draft: ModelWorkOrderDraft,
        session: AsyncSession,
        *,
        description: str,
    ) -> None:
        super().__init__(draft)
        self.session = session
        self.description = description

    async def ainvoke(
        self,
        payload: dict[str, Any],
        *,
        context: Any,
    ) -> dict[str, Any]:
        factory = _session_factory_for(self.session)
        async with factory() as other:
            complaint = await other.get(Complaint, context.complaint.id)
            assert complaint is not None
            complaint.description = self.description
            await other.commit()
        return await super().ainvoke(payload, context=context)


class RecordingChatModel:
    def __init__(self) -> None:
        self.invocations: list[list[Any]] = []
        self.bound_tool_names: list[str] = []
        self.bound_tool_descriptions: list[str] = []

    def bind_tools(
        self,
        tools: list[Any],
        **kwargs: Any,
    ) -> RecordingChatModel:
        self.bound_tool_names = [
            getattr(item, "name", "") for item in tools
        ]
        self.bound_tool_descriptions = [
            getattr(item, "description", "") for item in tools
        ]
        return self

    async def ainvoke(
        self,
        messages: Any,
        config: Any = None,
        **kwargs: Any,
    ) -> AIMessage:
        self.invocations.append(list(messages))
        return AIMessage(content="No tool calls required.")


@pytest.mark.asyncio
async def test_generation_holds_no_complaint_lock_during_model_calls(
    db_session: AsyncSession,
) -> None:
    admin, _ = await seed_admin(db_session)
    await _seed_skilled_technician(db_session)
    _, _, complaint = await _seed_ready_complaint(db_session)
    diagnosis = _diagnosis(complaint.id)
    service = WorkOrderProposalService(
        diagnostic_service=cast(
            DiagnosticService,
            LockProbeDiagnosticService(diagnosis),
        ),
        chat_model_factory=lambda: cast(Any, object()),
        max_tool_calls=3,
        max_model_calls=3,
        technician_limit=10,
        agent_builder=lambda **_: LockProbePreparationAgent(
            _draft(),
            db_session,
        ),
    )

    proposal = await service.generate(
        session=db_session,
        user=admin,
        vector_index=cast(Any, None),
        complaint_id=complaint.id,
    )
    await db_session.commit()

    assert proposal.status is WorkOrderProposalStatus.PENDING_APPROVAL


@pytest.mark.asyncio
async def test_generation_rejects_context_changed_during_preparation(
    db_session: AsyncSession,
) -> None:
    admin, _ = await seed_admin(db_session)
    await _seed_skilled_technician(db_session)
    _, _, complaint = await _seed_ready_complaint(db_session)
    complaint_id = complaint.id
    diagnosis = _diagnosis(complaint_id)
    service = WorkOrderProposalService(
        diagnostic_service=cast(
            DiagnosticService,
            StubDiagnosticService(diagnosis),
        ),
        chat_model_factory=lambda: cast(Any, object()),
        max_tool_calls=3,
        max_model_calls=3,
        technician_limit=10,
        agent_builder=lambda **_: ContextMutatingPreparationAgent(
            _draft(),
            db_session,
            description="A different failure mode was reported mid-flight.",
        ),
    )

    with pytest.raises(ProposalStaleError):
        await service.generate(
            session=db_session,
            user=admin,
            vector_index=cast(Any, None),
            complaint_id=complaint_id,
        )
    await db_session.rollback()

    count = await db_session.scalar(
        select(func.count(WorkOrderProposal.id)).where(
            WorkOrderProposal.complaint_id == complaint_id
        )
    )
    assert count == 0


@pytest.mark.parametrize(
    "field",
    [
        "description",
        "reported_error_code",
        "priority",
        "reported_symptoms",
    ],
)
@pytest.mark.asyncio
async def test_approval_rejects_stale_complaint_context(
    db_session: AsyncSession,
    field: str,
) -> None:
    admin, _ = await seed_admin(db_session)
    technician, _ = await _seed_skilled_technician(db_session)
    _, _, complaint = await _seed_ready_complaint(db_session)
    service = _service(_diagnosis(complaint.id))

    proposal = await service.generate(
        session=db_session,
        user=admin,
        vector_index=cast(Any, None),
        complaint_id=complaint.id,
    )
    await db_session.commit()
    proposal_id = proposal.id
    complaint_id = complaint.id

    if field == "description":
        complaint.description = "A different failure mode was reported."
    elif field == "reported_error_code":
        complaint.reported_error_code = "E-999"
    elif field == "priority":
        complaint.priority = Priority.URGENT
    else:
        complaint.reported_symptoms = ["new symptom"]
    await db_session.commit()

    with pytest.raises(ProposalStaleError):
        await service.approve(
            session=db_session,
            admin=admin,
            proposal_id=proposal_id,
            technician_id=technician.id,
        )
    await db_session.rollback()
    db_session.expire_all()

    refreshed = await db_session.get(WorkOrderProposal, proposal_id)
    assert refreshed is not None
    assert refreshed.status is WorkOrderProposalStatus.PENDING_APPROVAL
    work_order_count = await db_session.scalar(
        select(func.count(WorkOrder.id)).where(
            WorkOrder.complaint_id == complaint_id
        )
    )
    assert work_order_count == 0


@pytest.mark.asyncio
async def test_approval_rejects_changed_equipment_association(
    db_session: AsyncSession,
) -> None:
    admin, _ = await seed_admin(db_session)
    technician, _ = await _seed_skilled_technician(db_session)
    customer, _, complaint = await _seed_ready_complaint(db_session)
    service = _service(_diagnosis(complaint.id))

    proposal = await service.generate(
        session=db_session,
        user=admin,
        vector_index=cast(Any, None),
        complaint_id=complaint.id,
    )
    await db_session.commit()
    proposal_id = proposal.id
    complaint_id = complaint.id

    replacement = await seed_equipment(
        db_session,
        customer,
        model="INV-9000",
    )
    complaint.equipment_id = replacement.id
    await db_session.commit()

    with pytest.raises(ProposalStaleError):
        await service.approve(
            session=db_session,
            admin=admin,
            proposal_id=proposal_id,
            technician_id=technician.id,
        )
    await db_session.rollback()
    db_session.expire_all()

    refreshed = await db_session.get(WorkOrderProposal, proposal_id)
    assert refreshed is not None
    assert refreshed.status is WorkOrderProposalStatus.PENDING_APPROVAL
    work_order_count = await db_session.scalar(
        select(func.count(WorkOrder.id)).where(
            WorkOrder.complaint_id == complaint_id
        )
    )
    assert work_order_count == 0


@pytest.mark.asyncio
async def test_approval_rejects_changed_equipment_attributes(
    db_session: AsyncSession,
) -> None:
    admin, _ = await seed_admin(db_session)
    technician, _ = await _seed_skilled_technician(db_session)
    _, equipment, complaint = await _seed_ready_complaint(db_session)
    service = _service(_diagnosis(complaint.id))

    proposal = await service.generate(
        session=db_session,
        user=admin,
        vector_index=cast(Any, None),
        complaint_id=complaint.id,
    )
    await db_session.commit()
    proposal_id = proposal.id

    equipment.model = "INV-7000"
    await db_session.commit()

    with pytest.raises(ProposalStaleError):
        await service.approve(
            session=db_session,
            admin=admin,
            proposal_id=proposal_id,
            technician_id=technician.id,
        )


@pytest.mark.asyncio
async def test_approval_allows_unrelated_metadata_change(
    db_session: AsyncSession,
) -> None:
    admin, _ = await seed_admin(db_session)
    _, _, complaint = await _seed_ready_complaint(db_session)
    service = _service(_diagnosis(complaint.id))

    proposal = await service.generate(
        session=db_session,
        user=admin,
        vector_index=cast(Any, None),
        complaint_id=complaint.id,
    )
    await db_session.commit()

    complaint.channel = ComplaintChannel.WHATSAPP
    await db_session.commit()

    approved = await service.approve(
        session=db_session,
        admin=admin,
        proposal_id=proposal.id,
        technician_id=None,
    )
    await db_session.commit()

    assert approved.status is WorkOrderProposalStatus.APPROVED


@pytest.mark.asyncio
async def test_model_payload_excludes_technician_identity(
    db_session: AsyncSession,
) -> None:
    _, technician, _ = await seed_technician(
        db_session,
        full_name="Zelda Confidential Technician",
    )
    technician.skills = {"equipment_types": ["solar_inverter"]}
    technician.is_available = True
    await db_session.commit()
    _, _, complaint = await _seed_ready_complaint(db_session)
    equipment = await db_session.get(Equipment, complaint.equipment_id)
    assert equipment is not None

    diagnosis = _diagnosis(complaint.id)
    context = PreparationContext(
        complaint=complaint,
        equipment=equipment,
        diagnosis=diagnosis,
        required_skills=("solar_inverter",),
    )
    messages = build_preparation_message(
        complaint=complaint,
        equipment=equipment,
        diagnosis=diagnosis,
        required_skills=("solar_inverter",),
    )
    model = RecordingChatModel()
    agent = build_work_order_preparation_agent(
        chat_model=cast(Any, model),
        tools=build_work_order_preparation_tools(),
        max_tool_calls=3,
        max_model_calls=3,
    )
    with contextlib.suppress(Exception):
        await agent.ainvoke({"messages": messages}, context=context)

    assert model.invocations
    payload = json.dumps(
        {
            "messages": [
                str(message.content) for message in model.invocations[0]
            ],
            "tools": model.bound_tool_names,
            "tool_descriptions": model.bound_tool_descriptions,
        },
        default=str,
    )
    assert "Zelda Confidential Technician" not in payload
    assert str(technician.id) not in payload
    assert str(technician.user_id) not in payload
    assert technician.user.email not in payload
    assert "get_technician_candidates" not in payload
    for forbidden in (
        "matching_skills",
        "active_workload",
        "availability_status",
    ):
        assert forbidden not in payload


@pytest.mark.asyncio
async def test_concurrent_generation_creates_one_pending_proposal(
    migrated_db_session: AsyncSession,
    api_client: Any,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)
    await _seed_skilled_technician(migrated_db_session)
    _, _, complaint = await _seed_ready_complaint(migrated_db_session)
    complaint_id = complaint.id
    service = _service(_diagnosis(complaint_id))
    app.dependency_overrides[get_work_order_proposal_service] = lambda: service

    async def generate_proposal():
        return await api_client.post(
            f"/api/v1/admin/complaints/{complaint_id}/work-order-proposals",
            headers=bearer(admin_token),
        )

    first, second = await asyncio.gather(
        generate_proposal(),
        generate_proposal(),
    )
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [201, 409]
    losing = first if first.status_code == 409 else second
    assert losing.json()["error"]["code"] in {
        "proposal_already_pending",
        "proposal_conflict",
        "proposal_stale",
    }

    await migrated_db_session.rollback()
    count = await migrated_db_session.scalar(
        select(func.count(WorkOrderProposal.id)).where(
            WorkOrderProposal.complaint_id == complaint_id
        )
    )
    assert count == 1


@pytest.mark.asyncio
async def test_concurrent_approval_creates_one_work_order(
    migrated_db_session: AsyncSession,
    api_client: Any,
) -> None:
    admin, admin_token = await seed_admin(migrated_db_session)
    admin_id = admin.id
    technician, _ = await _seed_skilled_technician(migrated_db_session)
    _, _, complaint = await _seed_ready_complaint(migrated_db_session)
    complaint_id = complaint.id
    service = _service(_diagnosis(complaint_id))

    proposal = await service.generate(
        session=migrated_db_session,
        user=admin,
        vector_index=cast(Any, None),
        complaint_id=complaint_id,
    )
    await migrated_db_session.commit()
    proposal_id = proposal.id
    app.dependency_overrides[get_work_order_proposal_service] = lambda: service

    async def approve_proposal():
        return await api_client.post(
            f"/api/v1/admin/work-order-proposals/{proposal_id}/approve",
            json={"technician_id": str(technician.id)},
            headers=bearer(admin_token),
        )

    first, second = await asyncio.gather(
        approve_proposal(),
        approve_proposal(),
    )
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409]
    losing = first if first.status_code == 409 else second
    assert losing.json()["error"]["code"] in {
        "invalid_proposal_state",
        "proposal_conflict",
    }

    await migrated_db_session.rollback()
    migrated_db_session.expire_all()
    work_orders = (
        await migrated_db_session.execute(
            select(WorkOrder).where(
                WorkOrder.complaint_id == complaint_id
            )
        )
    ).scalars().all()
    assert len(work_orders) == 1
    work_order = work_orders[0]
    active_count = await migrated_db_session.scalar(
        select(func.count(TechnicianAssignment.id)).where(
            TechnicianAssignment.work_order_id == work_order.id,
            TechnicianAssignment.assignment_status.in_(
                [
                    AssignmentStatus.OFFERED,
                    AssignmentStatus.ACCEPTED,
                ]
            ),
        )
    )
    assert active_count == 1

    refreshed = await migrated_db_session.get(WorkOrderProposal, proposal_id)
    assert refreshed is not None
    assert refreshed.status is WorkOrderProposalStatus.APPROVED
    assert refreshed.reviewed_by_id == admin_id
    assert refreshed.resulting_work_order_id == work_order.id
    assert refreshed.resulting_assignment_id is not None


@pytest.mark.asyncio
async def test_approval_rolls_back_when_assignment_creation_fails(
    migrated_db_session: AsyncSession,
    api_client: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, admin_token = await seed_admin(migrated_db_session)
    technician, _ = await _seed_skilled_technician(migrated_db_session)
    _, _, complaint = await _seed_ready_complaint(migrated_db_session)
    complaint_id = complaint.id
    service = _service(_diagnosis(complaint_id))

    proposal = await service.generate(
        session=migrated_db_session,
        user=admin,
        vector_index=cast(Any, None),
        complaint_id=complaint_id,
    )
    await migrated_db_session.commit()
    proposal_id = proposal.id
    app.dependency_overrides[get_work_order_proposal_service] = lambda: service

    async def fail_assignment(*args: Any, **kwargs: Any) -> Any:
        raise assignment_service.TechnicianNotEligibleError(
            "simulated assignment creation failure"
        )

    monkeypatch.setattr(
        assignment_service,
        "create_assignment",
        fail_assignment,
    )

    response = await api_client.post(
        f"/api/v1/admin/work-order-proposals/{proposal_id}/approve",
        json={"technician_id": str(technician.id)},
        headers=bearer(admin_token),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "technician_not_eligible"

    await migrated_db_session.rollback()
    migrated_db_session.expire_all()
    work_order_count = await migrated_db_session.scalar(
        select(func.count(WorkOrder.id)).where(
            WorkOrder.complaint_id == complaint_id
        )
    )
    assert work_order_count == 0
    assignment_count = await migrated_db_session.scalar(
        select(func.count(TechnicianAssignment.id))
        .join(
            WorkOrder,
            TechnicianAssignment.work_order_id == WorkOrder.id,
        )
        .where(WorkOrder.complaint_id == complaint_id)
    )
    assert assignment_count == 0

    refreshed = await migrated_db_session.get(WorkOrderProposal, proposal_id)
    assert refreshed is not None
    assert refreshed.status is WorkOrderProposalStatus.PENDING_APPROVAL
    assert refreshed.reviewed_by_id is None
    assert refreshed.reviewed_at is None
    assert refreshed.selected_technician_id is None
    assert refreshed.resulting_work_order_id is None
    assert refreshed.resulting_assignment_id is None

    complaint_after = await migrated_db_session.get(Complaint, complaint_id)
    assert complaint_after is not None
    assert complaint_after.status is ComplaintStatus.READY_FOR_WORK_ORDER
