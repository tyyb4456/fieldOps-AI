from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.complaint_history import ComplaintHistory
from app.models.enums import (
    ComplaintStatus,
    Priority,
    WorkOrderProposalStatus,
)
from app.models.work_order_proposal import WorkOrderProposal
from app.schemas.work_orders.work_order import WorkOrderCreate
from app.services.complaints import lifecycle_service
from app.services.complaints.lifecycle import (
    ComplaintStatusConflictError,
    DiagnosticNotReadyError,
    DiagnosticStaleError,
    InvalidComplaintStatusTransitionError,
    LifecycleActor,
    LifecycleValidationError,
    PendingProposalConflictError,
    ReadinessMarker,
    ReadinessOperation,
    ReadinessProvenance,
    TerminalComplaintError,
)
from app.services.work_orders import work_orders as work_order_service
from tests.support import (
    seed_admin,
    seed_complaint,
    seed_customer,
    seed_equipment,
)

FINGERPRINT = "a" * 64


def _marker(
    *,
    run_id: uuid.UUID | None = None,
    fingerprint: str = FINGERPRINT,
) -> ReadinessMarker:
    return ReadinessMarker(
        readiness_source="lifecycle_v1",
        diagnostic_workflow_run_id=str(run_id or uuid.uuid4()),
        diagnostic_context_fingerprint=fingerprint,
        diagnostic_context_fingerprint_version=1,
        diagnostic_evidence_revision=1,
    )


def _proposal(complaint_id: uuid.UUID, **overrides: object) -> WorkOrderProposal:
    values: dict[str, object] = {
        "complaint_id": complaint_id,
        "status": WorkOrderProposalStatus.PENDING_APPROVAL,
        "title": "Inspect inverter",
        "problem_description": "Inverter offline",
        "proposed_scope": "Diagnose and repair",
        "technical_findings": "No DC output",
        "priority": Priority.NORMAL,
        "diagnostic_status": "diagnosed",
        "diagnostic_summary": "Diagnosis complete",
    }
    values.update(overrides)
    return WorkOrderProposal(**values)


async def _history(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> list[ComplaintHistory]:
    return list(
        (
            await session.scalars(
                select(ComplaintHistory)
                .where(ComplaintHistory.complaint_id == complaint_id)
                .order_by(ComplaintHistory.sequence_number)
            )
        ).all()
    )


async def test_transition_appends_sequenced_history(
    db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(db_session)
    equipment = await seed_equipment(db_session, customer)
    complaint = await seed_complaint(
        db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.RECEIVED,
    )
    admin, _ = await seed_admin(db_session)

    first = await lifecycle_service.transition_complaint(
        db_session,
        complaint_id=complaint.id,
        target_status=ComplaintStatus.ANALYZING,
        actor=LifecycleActor.ADMIN,
        actor_id=admin.id,
    )
    second = await lifecycle_service.transition_complaint(
        db_session,
        complaint_id=complaint.id,
        target_status=ComplaintStatus.AWAITING_CUSTOMER,
        actor=LifecycleActor.ADMIN,
        actor_id=admin.id,
        fields={"reason": "Need a photo of the error display"},
    )

    assert first.history.from_status is ComplaintStatus.RECEIVED
    assert first.history.to_status is ComplaintStatus.ANALYZING
    assert first.history.sequence_number == 1
    assert first.history.event_type == "investigation_requested"
    assert second.complaint.status is ComplaintStatus.AWAITING_CUSTOMER
    assert second.history.sequence_number == 2
    assert second.history.event_type == "clarification_requested"
    assert second.history.changed_fields["reason"] == (
        "Need a photo of the error display"
    )


async def test_expected_status_conflict_leaves_state_unchanged(
    db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(db_session)
    equipment = await seed_equipment(db_session, customer)
    complaint = await seed_complaint(
        db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.RECEIVED,
    )
    admin, _ = await seed_admin(db_session)

    with pytest.raises(ComplaintStatusConflictError):
        await lifecycle_service.transition_complaint(
            db_session,
            complaint_id=complaint.id,
            target_status=ComplaintStatus.ANALYZING,
            actor=LifecycleActor.ADMIN,
            actor_id=admin.id,
            expected_status=ComplaintStatus.ANALYZING,
        )

    await db_session.refresh(complaint)
    assert complaint.status is ComplaintStatus.RECEIVED
    assert await _history(db_session, complaint.id) == []


async def test_terminal_complaint_rejects_transitions(
    db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(db_session)
    complaint = await seed_complaint(
        db_session,
        customer,
        status=ComplaintStatus.CANCELLED,
    )
    admin, _ = await seed_admin(db_session)

    with pytest.raises(TerminalComplaintError):
        await lifecycle_service.transition_complaint(
            db_session,
            complaint_id=complaint.id,
            target_status=ComplaintStatus.ANALYZING,
            actor=LifecycleActor.ADMIN,
            actor_id=admin.id,
        )


async def test_readiness_transition_requires_complete_server_marker(
    db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(db_session)
    equipment = await seed_equipment(db_session, customer)
    complaint = await seed_complaint(
        db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.ANALYZING,
    )
    admin, _ = await seed_admin(db_session)

    with pytest.raises(DiagnosticNotReadyError):
        await lifecycle_service.transition_complaint(
            db_session,
            complaint_id=complaint.id,
            target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
            actor=LifecycleActor.ADMIN,
            actor_id=admin.id,
        )

    with pytest.raises(DiagnosticNotReadyError):
        await lifecycle_service.transition_complaint(
            db_session,
            complaint_id=complaint.id,
            target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
            actor=LifecycleActor.ADMIN,
            actor_id=admin.id,
            readiness_marker=_marker(fingerprint="too-short"),
        )

    with pytest.raises(LifecycleValidationError):
        await lifecycle_service.transition_complaint(
            db_session,
            complaint_id=complaint.id,
            target_status=ComplaintStatus.AWAITING_CUSTOMER,
            actor=LifecycleActor.ADMIN,
            actor_id=admin.id,
            fields={"reason": "Need more detail"},
            readiness_marker=_marker(),
        )

    await db_session.refresh(complaint)
    assert complaint.status is ComplaintStatus.ANALYZING


async def test_readiness_transition_records_lifecycle_provenance(
    db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(db_session)
    equipment = await seed_equipment(db_session, customer)
    complaint = await seed_complaint(
        db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.ANALYZING,
    )
    admin, _ = await seed_admin(db_session)
    marker = _marker()

    transition = await lifecycle_service.transition_complaint(
        db_session,
        complaint_id=complaint.id,
        target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
        actor=LifecycleActor.ADMIN,
        actor_id=admin.id,
        readiness_marker=marker,
    )

    assert transition.complaint.status is ComplaintStatus.READY_FOR_WORK_ORDER
    assert transition.history.changed_fields["readiness_source"] == "lifecycle_v1"
    assert (
        transition.history.changed_fields["diagnostic_workflow_run_id"]
        == marker.diagnostic_workflow_run_id
    )
    assert (
        transition.history.changed_fields["diagnostic_context_fingerprint"]
        == FINGERPRINT
    )

    record = await lifecycle_service.load_readiness_record(db_session, complaint.id)
    assert record.marker is not None
    assert record.marker.is_complete_lifecycle_provenance()
    assert record.has_lifecycle_marker_anywhere is True


async def test_customer_cancellation_supersedes_pending_proposal(
    db_session: AsyncSession,
) -> None:
    user, customer, _ = await seed_customer(db_session)
    equipment = await seed_equipment(db_session, customer)
    complaint = await seed_complaint(
        db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    proposal = _proposal(complaint.id)
    db_session.add(proposal)
    await db_session.commit()

    transition = await lifecycle_service.cancel_complaint(
        db_session,
        complaint_id=complaint.id,
        actor=LifecycleActor.CUSTOMER,
        actor_id=user.id,
        reason="Customer no longer needs the repair",
    )

    await db_session.refresh(proposal)
    assert transition.complaint.status is ComplaintStatus.CANCELLED
    assert transition.superseded_proposal_id == proposal.id
    assert proposal.status is WorkOrderProposalStatus.SUPERSEDED
    assert proposal.superseded_by_id == user.id
    assert proposal.superseded_at is not None
    assert proposal.supersession_reason == "customer_cancelled"
    assert proposal.reviewed_by_id is None
    assert proposal.reviewed_at is None
    assert proposal.rejection_reason is None
    assert transition.history.changed_fields["superseded_proposal_id"] == str(
        proposal.id
    )
    assert transition.history.changed_fields["supersession_reason"] == (
        "customer_cancelled"
    )


async def test_admin_escalation_supersedes_without_overwriting_review(
    db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(db_session)
    equipment = await seed_equipment(db_session, customer)
    complaint = await seed_complaint(
        db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    admin, _ = await seed_admin(db_session)
    reviewed_at = datetime(2026, 1, 1, tzinfo=UTC)
    proposal = _proposal(
        complaint.id,
        reviewed_by_id=admin.id,
        reviewed_at=reviewed_at,
        rejection_reason="Historical value",
    )
    db_session.add(proposal)
    await db_session.commit()

    transition = await lifecycle_service.transition_complaint(
        db_session,
        complaint_id=complaint.id,
        target_status=ComplaintStatus.ESCALATED,
        actor=LifecycleActor.ADMIN,
        actor_id=admin.id,
        fields={"reason": "Safety risk requires escalation"},
    )

    await db_session.refresh(proposal)
    assert transition.complaint.status is ComplaintStatus.ESCALATED
    assert proposal.status is WorkOrderProposalStatus.SUPERSEDED
    assert proposal.supersession_reason == "complaint_status_changed:escalated"
    assert proposal.reviewed_by_id == admin.id
    assert proposal.reviewed_at is not None
    assert proposal.rejection_reason == "Historical value"


async def test_conversion_does_not_supersede_pending_proposal(
    db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(db_session)
    equipment = await seed_equipment(db_session, customer)
    complaint = await seed_complaint(
        db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    admin, _ = await seed_admin(db_session)
    proposal = _proposal(complaint.id)
    db_session.add(proposal)
    await db_session.commit()

    locked = await lifecycle_service.lock_complaint(db_session, complaint.id)
    transition = await lifecycle_service.convert_locked_complaint(
        db_session,
        complaint=locked,
        actor_id=admin.id,
    )

    await db_session.refresh(proposal)
    assert transition.complaint.status is ComplaintStatus.CONVERTED
    assert transition.superseded_proposal_id is None
    assert proposal.status is WorkOrderProposalStatus.PENDING_APPROVAL


async def test_direct_conversion_aborts_when_proposal_pending(
    db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(db_session)
    equipment = await seed_equipment(db_session, customer)
    complaint = await seed_complaint(
        db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    admin, _ = await seed_admin(db_session)
    proposal = _proposal(complaint.id)
    db_session.add(proposal)
    await db_session.commit()

    with pytest.raises(PendingProposalConflictError):
        await work_order_service.create_work_order_from_complaint(
            db_session,
            complaint_id=complaint.id,
            data=WorkOrderCreate(
                title="Inspect inverter",
                description="Diagnose the DC input.",
            ),
            actor_id=admin.id,
        )

    await db_session.refresh(complaint)
    await db_session.refresh(proposal)
    assert complaint.status is ComplaintStatus.READY_FOR_WORK_ORDER
    assert proposal.status is WorkOrderProposalStatus.PENDING_APPROVAL


async def test_supersede_is_noop_for_reviewed_proposal(
    db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(db_session)
    complaint = await seed_complaint(db_session, customer)
    proposal = _proposal(
        complaint.id,
        status=WorkOrderProposalStatus.APPROVED,
    )
    db_session.add(proposal)
    await db_session.commit()

    changed = await lifecycle_service.supersede_pending_proposal(
        db_session,
        proposal=proposal,
        actor_id=None,
        reason="customer_cancelled",
    )

    await db_session.refresh(proposal)
    assert changed is False
    assert proposal.status is WorkOrderProposalStatus.APPROVED
    assert proposal.superseded_at is None


async def test_readiness_classification_prefers_lifecycle_marker(
    db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(db_session)
    equipment = await seed_equipment(db_session, customer)
    complaint = await seed_complaint(
        db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    await db_session.refresh(complaint)
    settings = Settings(
        lifecycle_readiness_enforced_at=datetime(2100, 1, 1, tzinfo=UTC),
        lifecycle_legacy_ready_ids=str(complaint.id),
    )
    await lifecycle_service.append_history(
        db_session,
        complaint_id=complaint.id,
        event_type="ready_for_work_order",
        from_status=ComplaintStatus.ANALYZING,
        to_status=ComplaintStatus.READY_FOR_WORK_ORDER,
        changed_fields={
            "readiness_source": "lifecycle_v1",
            "diagnostic_workflow_run_id": str(uuid.uuid4()),
            "diagnostic_context_fingerprint": FINGERPRINT,
            "diagnostic_context_fingerprint_version": 1,
            "diagnostic_evidence_revision": 1,
        },
        actor_id=None,
    )

    _, provenance = await lifecycle_service.classify_readiness(
        db_session,
        complaint,
        settings=settings,
    )
    _, decision = await lifecycle_service.evaluate_readiness(
        db_session,
        complaint,
        operation=ReadinessOperation.DIRECT_CONVERSION,
        settings=settings,
    )

    assert provenance is ReadinessProvenance.LIFECYCLE
    assert decision.requires_diagnostic_revalidation is True
    assert decision.uses_legacy_exception is False


async def test_readiness_classification_legacy_exception(
    db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(db_session)
    equipment = await seed_equipment(db_session, customer)
    complaint = await seed_complaint(
        db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    await db_session.refresh(complaint)
    settings = Settings(
        lifecycle_readiness_enforced_at=datetime(2100, 1, 1, tzinfo=UTC),
        lifecycle_legacy_ready_ids=str(complaint.id),
    )

    _, provenance = await lifecycle_service.classify_readiness(
        db_session,
        complaint,
        settings=settings,
    )
    _, decision = await lifecycle_service.evaluate_readiness(
        db_session,
        complaint,
        operation=ReadinessOperation.PROPOSAL_APPROVAL,
        settings=settings,
    )

    assert provenance is ReadinessProvenance.LEGACY_ELIGIBLE
    assert decision.uses_legacy_exception is True
    assert decision.requires_diagnostic_revalidation is False

    with pytest.raises(DiagnosticNotReadyError):
        await lifecycle_service.evaluate_readiness(
            db_session,
            complaint,
            operation=ReadinessOperation.READINESS_CONFIRMATION,
            settings=settings,
        )


async def test_readiness_classification_rejects_corrupt_and_ineligible(
    db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(db_session)
    equipment = await seed_equipment(db_session, customer)
    complaint = await seed_complaint(
        db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    await db_session.refresh(complaint)
    await lifecycle_service.append_history(
        db_session,
        complaint_id=complaint.id,
        event_type="ready_for_work_order",
        from_status=ComplaintStatus.ANALYZING,
        to_status=ComplaintStatus.READY_FOR_WORK_ORDER,
        changed_fields={
            "readiness_source": "lifecycle_v1",
            "diagnostic_workflow_run_id": str(uuid.uuid4()),
            "diagnostic_context_fingerprint": "not-a-fingerprint",
        },
        actor_id=None,
    )
    settings = Settings(
        lifecycle_readiness_enforced_at=datetime(2100, 1, 1, tzinfo=UTC),
        lifecycle_legacy_ready_ids=str(complaint.id),
    )

    _, provenance = await lifecycle_service.classify_readiness(
        db_session,
        complaint,
        settings=settings,
    )
    assert provenance is ReadinessProvenance.LIFECYCLE_CORRUPT
    with pytest.raises(DiagnosticStaleError):
        await lifecycle_service.evaluate_readiness(
            db_session,
            complaint,
            operation=ReadinessOperation.DIRECT_CONVERSION,
            settings=settings,
        )

    await lifecycle_service.append_history(
        db_session,
        complaint_id=complaint.id,
        event_type="ready_for_work_order",
        from_status=ComplaintStatus.ANALYZING,
        to_status=ComplaintStatus.READY_FOR_WORK_ORDER,
        changed_fields={"status": {"from": "analyzing", "to": "ready_for_work_order"}},
        actor_id=None,
    )
    _, ineligible = await lifecycle_service.classify_readiness(
        db_session,
        complaint,
        settings=settings,
    )
    assert ineligible is ReadinessProvenance.NOT_ELIGIBLE


async def test_readiness_confirmation_rejects_ineligible_source_status(
    db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(db_session)
    complaint = await seed_complaint(
        db_session,
        customer,
        status=ComplaintStatus.RECEIVED,
    )
    admin, _ = await seed_admin(db_session)

    with pytest.raises(InvalidComplaintStatusTransitionError):
        await lifecycle_service.transition_complaint(
            db_session,
            complaint_id=complaint.id,
            target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
            actor=LifecycleActor.ADMIN,
            actor_id=admin.id,
            readiness_marker=_marker(),
        )
