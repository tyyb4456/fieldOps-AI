from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.complaint_history import ComplaintHistory
from app.models.document import Document
from app.models.enums import (
    ComplaintStatus,
    IngestionStatus,
    Priority,
    WorkOrderStatus,
)
from app.models.service_record import ServiceRecord
from app.models.work_order import WorkOrder
from app.services.complaints import lifecycle_service
from app.services.complaints.admin_lifecycle import (
    transition_complaint_as_admin,
)
from app.services.complaints.lifecycle import (
    ComplaintStatusConflictError,
    DiagnosticNotReadyError,
    DiagnosticStaleError,
    EquipmentRequiredError,
    InvalidComplaintStatusTransitionError,
    LifecycleEvent,
    LifecycleValidationError,
    ReadinessOperation,
    TerminalComplaintError,
    validate_transition,
)
from app.services.complaints.readiness import (
    validate_readiness_for_operation,
)
from app.services.diagnostics.readiness_context import (
    compute_diagnostic_context,
)
from tests.support import (
    seed_admin,
    seed_complaint,
    seed_completed_diagnostic_run,
    seed_customer,
    seed_equipment,
    seed_ready_complaint,
    seed_technician,
)


async def _seed_analyzing_complaint(
    session: AsyncSession,
    *,
    equipment: bool = True,
    **run_kwargs: object,
):
    _, customer, _ = await seed_customer(session)
    resolved_equipment = (
        await seed_equipment(session, customer) if equipment else None
    )
    complaint = await seed_complaint(
        session,
        customer,
        equipment=resolved_equipment,
        status=ComplaintStatus.ANALYZING,
    )
    run = None
    if resolved_equipment is not None:
        run = await seed_completed_diagnostic_run(
            session,
            complaint,
            resolved_equipment,
            **run_kwargs,
        )
    return complaint, resolved_equipment, run


async def _lock(session: AsyncSession, complaint_id: uuid.UUID):
    return await lifecycle_service.lock_complaint(session, complaint_id)


@pytest.mark.asyncio
async def test_admin_confirmation_records_lifecycle_provenance(
    migrated_db_session: AsyncSession,
) -> None:
    complaint, _, run = await _seed_analyzing_complaint(migrated_db_session)
    admin, _ = await seed_admin(migrated_db_session)
    assert run is not None

    transition = await transition_complaint_as_admin(
        migrated_db_session,
        complaint_id=complaint.id,
        target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
        expected_status=ComplaintStatus.ANALYZING,
        fields={"reason": "Diagnostic supports readiness."},
        actor_id=admin.id,
    )
    await migrated_db_session.commit()

    assert transition.complaint.status is ComplaintStatus.READY_FOR_WORK_ORDER
    assert transition.history.event_type == "ready_for_work_order"
    assert transition.history.changed_fields["readiness_source"] == "lifecycle_v1"
    assert (
        transition.history.changed_fields["diagnostic_workflow_run_id"]
        == str(run.id)
    )
    assert (
        transition.history.changed_fields["diagnostic_context_fingerprint"]
        == run.input_payload["context_fingerprint"]
    )
    assert transition.history.changed_fields["reason"] == (
        "Diagnostic supports readiness."
    )


@pytest.mark.asyncio
async def test_admin_confirmation_requires_equipment(
    migrated_db_session: AsyncSession,
) -> None:
    complaint, _, _ = await _seed_analyzing_complaint(
        migrated_db_session,
        equipment=False,
    )
    complaint_id = complaint.id
    admin, _ = await seed_admin(migrated_db_session)

    with pytest.raises(EquipmentRequiredError) as excinfo:
        await transition_complaint_as_admin(
            migrated_db_session,
            complaint_id=complaint_id,
            target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
            expected_status=ComplaintStatus.ANALYZING,
            actor_id=admin.id,
        )
    await migrated_db_session.rollback()

    assert excinfo.value.code.value == "equipment_required"
    refreshed = await migrated_db_session.get(type(complaint), complaint_id)
    assert refreshed is not None
    assert refreshed.status is ComplaintStatus.ANALYZING
    history_count = await migrated_db_session.scalar(
        select(ComplaintHistory.id).where(
            ComplaintHistory.complaint_id == complaint_id
        )
    )
    assert history_count is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("run_kwargs", "expected_code"),
    [
        ({"result_status": "needs_information"}, "diagnostic_not_ready"),
        ({"requires_escalation": True}, "diagnostic_not_ready"),
        ({"lifecycle_phase": "post_conversion"}, "diagnostic_not_ready"),
        ({"lifecycle_phase": "unknown_phase"}, "diagnostic_not_ready"),
        ({"lifecycle_phase": ""}, "diagnostic_not_ready"),
    ],
)
async def test_admin_confirmation_rejects_non_qualifying_diagnostics(
    migrated_db_session: AsyncSession,
    run_kwargs: dict[str, object],
    expected_code: str,
) -> None:
    complaint, _, _ = await _seed_analyzing_complaint(
        migrated_db_session,
        **run_kwargs,
    )
    complaint_id = complaint.id
    admin, _ = await seed_admin(migrated_db_session)

    with pytest.raises(DiagnosticNotReadyError) as excinfo:
        await transition_complaint_as_admin(
            migrated_db_session,
            complaint_id=complaint_id,
            target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
            expected_status=ComplaintStatus.ANALYZING,
            actor_id=admin.id,
        )
    await migrated_db_session.rollback()

    assert excinfo.value.code.value == expected_code
    refreshed = await migrated_db_session.get(type(complaint), complaint_id)
    assert refreshed is not None
    assert refreshed.status is ComplaintStatus.ANALYZING


@pytest.mark.asyncio
async def test_admin_confirmation_rejects_missing_lifecycle_phase(
    migrated_db_session: AsyncSession,
) -> None:
    complaint, _, run = await _seed_analyzing_complaint(migrated_db_session)
    assert run is not None
    payload = dict(run.input_payload)
    payload.pop("lifecycle_phase", None)
    run.input_payload = payload
    await migrated_db_session.commit()
    complaint_id = complaint.id
    admin, _ = await seed_admin(migrated_db_session)

    with pytest.raises(DiagnosticNotReadyError):
        await transition_complaint_as_admin(
            migrated_db_session,
            complaint_id=complaint_id,
            target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
            expected_status=ComplaintStatus.ANALYZING,
            actor_id=admin.id,
        )
    await migrated_db_session.rollback()

    refreshed = await migrated_db_session.get(type(complaint), complaint_id)
    assert refreshed is not None
    assert refreshed.status is ComplaintStatus.ANALYZING
    history_count = await migrated_db_session.scalar(
        select(func.count(ComplaintHistory.id)).where(
            ComplaintHistory.complaint_id == complaint_id
        )
    )
    assert history_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase_value",
    [
        None,
        1,
        True,
        ["pre_conversion"],
        {"value": "pre_conversion"},
    ],
)
async def test_admin_confirmation_rejects_malformed_lifecycle_phase(
    migrated_db_session: AsyncSession,
    phase_value: object,
) -> None:
    complaint, _, run = await _seed_analyzing_complaint(migrated_db_session)
    assert run is not None
    payload = dict(run.input_payload)
    payload["lifecycle_phase"] = phase_value
    run.input_payload = payload
    await migrated_db_session.commit()
    complaint_id = complaint.id
    admin, _ = await seed_admin(migrated_db_session)

    with pytest.raises(DiagnosticNotReadyError):
        await transition_complaint_as_admin(
            migrated_db_session,
            complaint_id=complaint_id,
            target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
            expected_status=ComplaintStatus.ANALYZING,
            actor_id=admin.id,
        )
    await migrated_db_session.rollback()

    refreshed = await migrated_db_session.get(type(complaint), complaint_id)
    assert refreshed is not None
    assert refreshed.status is ComplaintStatus.ANALYZING


@pytest.mark.asyncio
async def test_admin_confirmation_requires_a_completed_diagnostic(
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint = await seed_complaint(
        migrated_db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.ANALYZING,
    )
    admin, _ = await seed_admin(migrated_db_session)

    with pytest.raises(DiagnosticNotReadyError):
        await transition_complaint_as_admin(
            migrated_db_session,
            complaint_id=complaint.id,
            target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
            expected_status=ComplaintStatus.ANALYZING,
            actor_id=admin.id,
        )
    await migrated_db_session.rollback()


@pytest.mark.asyncio
async def test_admin_confirmation_rejects_non_latest_diagnostic(
    migrated_db_session: AsyncSession,
) -> None:
    complaint, equipment, older = await _seed_analyzing_complaint(
        migrated_db_session,
    )
    assert equipment is not None and older is not None
    newer = await seed_completed_diagnostic_run(
        migrated_db_session,
        complaint,
        equipment,
        finished_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    complaint_id = complaint.id
    older_id = older.id
    newer_id = newer.id
    admin, _ = await seed_admin(migrated_db_session)
    admin_id = admin.id

    with pytest.raises(DiagnosticNotReadyError):
        await transition_complaint_as_admin(
            migrated_db_session,
            complaint_id=complaint_id,
            target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
            expected_status=ComplaintStatus.ANALYZING,
            actor_id=admin_id,
            diagnostic_workflow_run_id=older_id,
        )
    await migrated_db_session.rollback()

    transition = await transition_complaint_as_admin(
        migrated_db_session,
        complaint_id=complaint_id,
        target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
        expected_status=ComplaintStatus.ANALYZING,
        actor_id=admin_id,
        diagnostic_workflow_run_id=newer_id,
    )
    await migrated_db_session.commit()

    assert transition.complaint.status is ComplaintStatus.READY_FOR_WORK_ORDER
    assert transition.history.changed_fields["diagnostic_workflow_run_id"] == (
        str(newer_id)
    )


@pytest.mark.asyncio
async def test_admin_transition_enforces_expected_status(
    migrated_db_session: AsyncSession,
) -> None:
    complaint, _, _ = await _seed_analyzing_complaint(migrated_db_session)
    admin, _ = await seed_admin(migrated_db_session)

    with pytest.raises(ComplaintStatusConflictError):
        await transition_complaint_as_admin(
            migrated_db_session,
            complaint_id=complaint.id,
            target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
            expected_status=ComplaintStatus.RECEIVED,
            actor_id=admin.id,
        )
    await migrated_db_session.rollback()


@pytest.mark.asyncio
async def test_admin_transition_rejects_invalid_edges_and_missing_fields(
    migrated_db_session: AsyncSession,
) -> None:
    complaint, _, _ = await _seed_analyzing_complaint(migrated_db_session)
    complaint_id = complaint.id
    admin, _ = await seed_admin(migrated_db_session)
    admin_id = admin.id

    with pytest.raises(InvalidComplaintStatusTransitionError):
        await transition_complaint_as_admin(
            migrated_db_session,
            complaint_id=complaint_id,
            target_status=ComplaintStatus.RECEIVED,
            expected_status=ComplaintStatus.ANALYZING,
            actor_id=admin_id,
        )
    await migrated_db_session.rollback()

    with pytest.raises(LifecycleValidationError):
        await transition_complaint_as_admin(
            migrated_db_session,
            complaint_id=complaint_id,
            target_status=ComplaintStatus.AWAITING_CUSTOMER,
            expected_status=ComplaintStatus.ANALYZING,
            actor_id=admin_id,
        )
    await migrated_db_session.rollback()


@pytest.mark.asyncio
async def test_admin_transition_rejects_terminal_complaint(
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint = await seed_complaint(
        migrated_db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.CLOSED,
    )
    admin, _ = await seed_admin(migrated_db_session)

    with pytest.raises(TerminalComplaintError):
        await transition_complaint_as_admin(
            migrated_db_session,
            complaint_id=complaint.id,
            target_status=ComplaintStatus.ANALYZING,
            expected_status=ComplaintStatus.CLOSED,
            actor_id=admin.id,
        )
    await migrated_db_session.rollback()


@pytest.mark.asyncio
async def test_readiness_reenforcement_detects_complaint_edit(
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint, _ = await seed_ready_complaint(
        migrated_db_session,
        customer,
        equipment,
    )

    complaint.description = "The inverter now reports a different fault."
    await migrated_db_session.commit()

    locked = await _lock(migrated_db_session, complaint.id)
    with pytest.raises(DiagnosticStaleError):
        await validate_readiness_for_operation(
            migrated_db_session,
            locked,
            operation=ReadinessOperation.DIRECT_CONVERSION,
        )
    await migrated_db_session.rollback()


@pytest.mark.asyncio
async def test_readiness_reenforcement_detects_equipment_change(
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint, _ = await seed_ready_complaint(
        migrated_db_session,
        customer,
        equipment,
    )

    equipment.model = "INV-9000"
    await migrated_db_session.commit()

    locked = await _lock(migrated_db_session, complaint.id)
    with pytest.raises(DiagnosticStaleError):
        await validate_readiness_for_operation(
            migrated_db_session,
            locked,
            operation=ReadinessOperation.PROPOSAL_APPROVAL,
        )
    await migrated_db_session.rollback()


@pytest.mark.asyncio
async def test_readiness_reenforcement_detects_new_evidence_history(
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint, _ = await seed_ready_complaint(
        migrated_db_session,
        customer,
        equipment,
    )

    await lifecycle_service.append_history(
        migrated_db_session,
        complaint_id=complaint.id,
        event_type=LifecycleEvent.CUSTOMER_RESPONDED.value,
        from_status=ComplaintStatus.READY_FOR_WORK_ORDER,
        to_status=ComplaintStatus.ANALYZING,
        changed_fields={"message": "Updated symptom."},
        actor_id=None,
    )
    await migrated_db_session.commit()

    locked = await _lock(migrated_db_session, complaint.id)
    with pytest.raises(DiagnosticStaleError):
        await validate_readiness_for_operation(
            migrated_db_session,
            locked,
            operation=ReadinessOperation.DIRECT_CONVERSION,
        )
    await migrated_db_session.rollback()


@pytest.mark.asyncio
async def test_readiness_reenforcement_detects_service_history_change(
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint, _ = await seed_ready_complaint(
        migrated_db_session,
        customer,
        equipment,
    )
    _, technician, _ = await seed_technician(migrated_db_session)
    other_complaint = await seed_complaint(
        migrated_db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.CONVERTED,
    )
    work_order = WorkOrder(
        complaint_id=other_complaint.id,
        equipment_id=equipment.id,
        title="Prior service",
        description="Prior service visit.",
        priority=Priority.NORMAL,
        status=WorkOrderStatus.COMPLETED,
    )
    migrated_db_session.add(work_order)
    await migrated_db_session.flush()
    migrated_db_session.add(
        ServiceRecord(
            equipment_id=equipment.id,
            work_order_id=work_order.id,
            technician_id=technician.id,
            findings="Replaced the DC fuse.",
            work_performed="Fuse replacement.",
            parts_used=[],
        )
    )
    await migrated_db_session.commit()

    locked = await _lock(migrated_db_session, complaint.id)
    with pytest.raises(DiagnosticStaleError):
        await validate_readiness_for_operation(
            migrated_db_session,
            locked,
            operation=ReadinessOperation.DIRECT_CONVERSION,
        )
    await migrated_db_session.rollback()


@pytest.mark.asyncio
async def test_readiness_reenforcement_detects_knowledge_corpus_change(
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint, _ = await seed_ready_complaint(
        migrated_db_session,
        customer,
        equipment,
    )
    migrated_db_session.add(
        Document(
            manufacturer=equipment.manufacturer,
            model=equipment.model,
            document_name="Service bulletin",
            version="1.0",
            ingestion_status=IngestionStatus.READY,
            is_active=True,
        )
    )
    await migrated_db_session.commit()

    locked = await _lock(migrated_db_session, complaint.id)
    with pytest.raises(DiagnosticStaleError):
        await validate_readiness_for_operation(
            migrated_db_session,
            locked,
            operation=ReadinessOperation.DIRECT_CONVERSION,
        )
    await migrated_db_session.rollback()


@pytest.mark.asyncio
async def test_context_fingerprint_covers_evidence_inputs(
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint = await seed_complaint(
        migrated_db_session,
        customer,
        equipment=equipment,
    )

    baseline = await compute_diagnostic_context(
        migrated_db_session,
        complaint,
        equipment,
    )
    migrated_db_session.add(
        Document(
            manufacturer=equipment.manufacturer,
            model=equipment.model,
            document_name="Service bulletin",
            version="1.0",
            ingestion_status=IngestionStatus.READY,
            is_active=True,
        )
    )
    await migrated_db_session.flush()
    changed = await compute_diagnostic_context(
        migrated_db_session,
        complaint,
        equipment,
    )

    assert changed.knowledge_corpus_digest != baseline.knowledge_corpus_digest
    assert changed.fingerprint != baseline.fingerprint


@pytest.mark.asyncio
async def test_legacy_exception_requires_allowlist_and_cutoff(
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint = await seed_complaint(
        migrated_db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    complaint_id = complaint.id
    settings = get_settings().model_copy(
        update={
            "lifecycle_readiness_enforced_at": datetime.now(UTC)
            + timedelta(days=1),
            "lifecycle_legacy_ready_ids": str(complaint_id),
        }
    )

    locked = await _lock(migrated_db_session, complaint_id)
    validation = await validate_readiness_for_operation(
        migrated_db_session,
        locked,
        operation=ReadinessOperation.DIRECT_CONVERSION,
        settings=settings,
    )
    await migrated_db_session.rollback()

    assert validation.uses_legacy_exception is True
    assert validation.audit_fields["legacy_readiness_exception"] is True

    not_allowlisted = settings.model_copy(
        update={"lifecycle_legacy_ready_ids": ""}
    )
    locked = await _lock(migrated_db_session, complaint_id)
    with pytest.raises(DiagnosticNotReadyError):
        await validate_readiness_for_operation(
            migrated_db_session,
            locked,
            operation=ReadinessOperation.DIRECT_CONVERSION,
            settings=not_allowlisted,
        )
    await migrated_db_session.rollback()

    after_cutoff = settings.model_copy(
        update={
            "lifecycle_readiness_enforced_at": datetime.now(UTC)
            - timedelta(days=1)
        }
    )
    locked = await _lock(migrated_db_session, complaint_id)
    with pytest.raises(DiagnosticNotReadyError):
        await validate_readiness_for_operation(
            migrated_db_session,
            locked,
            operation=ReadinessOperation.DIRECT_CONVERSION,
            settings=after_cutoff,
        )
    await migrated_db_session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase_mode",
    ["missing", "unknown", "malformed", "post_conversion"],
)
async def test_lifecycle_marker_with_invalid_phase_cannot_use_legacy_exception(
    migrated_db_session: AsyncSession,
    phase_mode: str,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint, run = await seed_ready_complaint(
        migrated_db_session,
        customer,
        equipment,
    )
    payload = dict(run.input_payload)
    if phase_mode == "missing":
        payload.pop("lifecycle_phase", None)
    elif phase_mode == "unknown":
        payload["lifecycle_phase"] = "unknown_phase"
    elif phase_mode == "malformed":
        payload["lifecycle_phase"] = ["pre_conversion"]
    else:
        payload["lifecycle_phase"] = "post_conversion"
    run.input_payload = payload
    await migrated_db_session.commit()

    settings = get_settings().model_copy(
        update={
            "lifecycle_readiness_enforced_at": datetime.now(UTC)
            + timedelta(days=1),
            "lifecycle_legacy_ready_ids": str(complaint.id),
        }
    )

    locked = await _lock(migrated_db_session, complaint.id)
    with pytest.raises(DiagnosticNotReadyError) as excinfo:
        await validate_readiness_for_operation(
            migrated_db_session,
            locked,
            operation=ReadinessOperation.DIRECT_CONVERSION,
            settings=settings,
        )
    await migrated_db_session.rollback()

    assert excinfo.value.code.value == "diagnostic_not_ready"


@pytest.mark.asyncio
async def test_legacy_exception_never_overrides_lifecycle_provenance(
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint, _ = await seed_ready_complaint(
        migrated_db_session,
        customer,
        equipment,
    )
    settings = get_settings().model_copy(
        update={
            "lifecycle_readiness_enforced_at": datetime.now(UTC)
            + timedelta(days=1),
            "lifecycle_legacy_ready_ids": str(complaint.id),
        }
    )

    latest = await migrated_db_session.scalar(
        select(ComplaintHistory)
        .where(
            ComplaintHistory.complaint_id == complaint.id,
            ComplaintHistory.to_status
            == ComplaintStatus.READY_FOR_WORK_ORDER,
        )
        .order_by(ComplaintHistory.sequence_number.desc())
        .limit(1)
    )
    assert latest is not None
    changed_fields = dict(latest.changed_fields)
    changed_fields["diagnostic_context_fingerprint"] = "not-a-fingerprint"
    latest.changed_fields = changed_fields
    await migrated_db_session.commit()

    locked = await _lock(migrated_db_session, complaint.id)
    with pytest.raises(DiagnosticStaleError):
        await validate_readiness_for_operation(
            migrated_db_session,
            locked,
            operation=ReadinessOperation.DIRECT_CONVERSION,
            settings=settings,
        )
    await migrated_db_session.rollback()


def test_validate_transition_requires_expected_status_match() -> None:
    with pytest.raises(ComplaintStatusConflictError):
        validate_transition(
            ComplaintStatus.ANALYZING,
            ComplaintStatus.READY_FOR_WORK_ORDER,
            "admin",
            expected_status=ComplaintStatus.RECEIVED,
        )
