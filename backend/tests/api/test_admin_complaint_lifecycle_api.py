from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.complaint_history import ComplaintHistory
from app.models.enums import ComplaintStatus
from app.models.technician_assignment import TechnicianAssignment
from app.models.work_order import WorkOrder
from app.models.workflow_run import WorkflowRun
from app.services.complaints import lifecycle_service
from tests.support import (
    bearer,
    seed_admin,
    seed_complaint,
    seed_completed_diagnostic_run,
    seed_customer,
    seed_equipment,
    seed_ready_complaint,
)

WORK_ORDER_PAYLOAD = {
    "title": "Inspect inverter error E-05",
    "description": "Reproduce the reported error and inspect DC inputs.",
    "diagnostic_checklist": [],
}

_MISSING_PHASE = object()


def _set_diagnostic_phase(run: WorkflowRun, phase: object) -> None:
    payload = dict(run.input_payload)
    if phase is _MISSING_PHASE:
        payload.pop("lifecycle_phase", None)
    else:
        payload["lifecycle_phase"] = phase
    run.input_payload = payload


async def _seed_analyzing_with_diagnostic(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, str]:
    _, customer, _ = await seed_customer(session)
    equipment = await seed_equipment(session, customer)
    complaint = await seed_complaint(
        session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.ANALYZING,
    )
    run = await seed_completed_diagnostic_run(session, complaint, equipment)
    _, admin_token = await seed_admin(session)
    return complaint.id, run.id, admin_token


@pytest.mark.asyncio
async def test_status_endpoint_requires_authentication(api_client) -> None:
    response = await api_client.post(
        f"/api/v1/admin/complaints/{uuid.uuid4()}/status",
        json={
            "status": "ready_for_work_order",
            "expected_status": "analyzing",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_status_endpoint_forbids_non_admin(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    complaint_id, _, _ = await _seed_analyzing_with_diagnostic(
        migrated_db_session
    )
    _, _, customer_token = await seed_customer(migrated_db_session)

    response = await api_client.post(
        f"/api/v1/admin/complaints/{complaint_id}/status",
        headers=bearer(customer_token),
        json={
            "status": "ready_for_work_order",
            "expected_status": "analyzing",
            "reason": "Diagnostic supports readiness.",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.asyncio
async def test_admin_confirms_readiness(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    complaint_id, run_id, admin_token = await _seed_analyzing_with_diagnostic(
        migrated_db_session
    )

    response = await api_client.post(
        f"/api/v1/admin/complaints/{complaint_id}/status",
        headers=bearer(admin_token),
        json={
            "status": "ready_for_work_order",
            "expected_status": "analyzing",
            "reason": "Diagnostic supports readiness.",
            "diagnostic_workflow_run_id": str(run_id),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["complaint"]["status"] == "ready_for_work_order"
    assert body["history"]["event_type"] == "ready_for_work_order"
    assert body["history"]["changed_fields"]["readiness_source"] == (
        "lifecycle_v1"
    )
    assert body["history"]["changed_fields"][
        "diagnostic_workflow_run_id"
    ] == str(run_id)
    assert "analyzing" in body["available_transitions"]


@pytest.mark.asyncio
async def test_status_endpoint_reports_missing_diagnostic(
    api_client,
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
    _, admin_token = await seed_admin(migrated_db_session)

    response = await api_client.post(
        f"/api/v1/admin/complaints/{complaint.id}/status",
        headers=bearer(admin_token),
        json={
            "status": "ready_for_work_order",
            "expected_status": "analyzing",
            "reason": "Diagnostic supports readiness.",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "diagnostic_not_ready"
    await migrated_db_session.rollback()
    refreshed = await migrated_db_session.get(type(complaint), complaint.id)
    assert refreshed is not None
    assert refreshed.status is ComplaintStatus.ANALYZING


@pytest.mark.asyncio
async def test_status_endpoint_reports_stale_fingerprint(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint, _ = await seed_ready_complaint(
        migrated_db_session,
        customer,
        equipment,
    )
    _, admin_token = await seed_admin(migrated_db_session)
    complaint.description = "A new symptom was reported after diagnosis."
    await migrated_db_session.commit()

    response = await api_client.post(
        f"/api/v1/admin/complaints/{complaint.id}/status",
        headers=bearer(admin_token),
        json={
            "status": "escalated",
            "expected_status": "ready_for_work_order",
            "reason": "Needs a supervisor.",
        },
    )

    assert response.status_code == 200, response.text

    response = await api_client.post(
        f"/api/v1/admin/complaints/{complaint.id}/status",
        headers=bearer(admin_token),
        json={
            "status": "ready_for_work_order",
            "expected_status": "escalated",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "diagnostic_stale"


@pytest.mark.asyncio
async def test_status_endpoint_reports_expected_status_conflict(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    complaint_id, _, admin_token = await _seed_analyzing_with_diagnostic(
        migrated_db_session
    )

    response = await api_client.post(
        f"/api/v1/admin/complaints/{complaint_id}/status",
        headers=bearer(admin_token),
        json={
            "status": "ready_for_work_order",
            "expected_status": "received",
            "reason": "Diagnostic supports readiness.",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "complaint_status_conflict"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {
            "status": "analyzing",
            "expected_status": "analyzing",
        },
        {
            "status": "received",
            "expected_status": "analyzing",
        },
        {
            "status": "awaiting_customer",
            "expected_status": "analyzing",
        },
        {
            "status": "closed",
            "expected_status": "analyzing",
        },
    ],
)
async def test_status_endpoint_rejects_invalid_payloads(
    api_client,
    migrated_db_session: AsyncSession,
    payload: dict[str, object],
) -> None:
    complaint_id, _, admin_token = await _seed_analyzing_with_diagnostic(
        migrated_db_session
    )

    response = await api_client.post(
        f"/api/v1/admin/complaints/{complaint_id}/status",
        headers=bearer(admin_token),
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_status_endpoint_returns_not_found(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)

    response = await api_client.post(
        f"/api/v1/admin/complaints/{uuid.uuid4()}/status",
        headers=bearer(admin_token),
        json={
            "status": "escalated",
            "expected_status": "analyzing",
            "reason": "Needs a supervisor.",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_direct_conversion_rejects_stale_readiness(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint, _ = await seed_ready_complaint(
        migrated_db_session,
        customer,
        equipment,
    )
    _, admin_token = await seed_admin(migrated_db_session)
    complaint.description = "The inverter now reports a different fault."
    await migrated_db_session.commit()

    response = await api_client.post(
        f"/api/v1/admin/complaints/{complaint.id}/work-orders",
        headers=bearer(admin_token),
        json=WORK_ORDER_PAYLOAD,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "diagnostic_stale"
    await migrated_db_session.rollback()
    work_order_count = await migrated_db_session.scalar(
        select(func.count(WorkOrder.id)).where(
            WorkOrder.complaint_id == complaint.id
        )
    )
    assert work_order_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase",
    [
        pytest.param(_MISSING_PHASE, id="missing"),
        pytest.param("unknown_phase", id="unknown"),
        pytest.param(["pre_conversion"], id="malformed"),
        pytest.param("post_conversion", id="post_conversion"),
    ],
)
async def test_direct_conversion_rejects_missing_or_invalid_phase(
    api_client,
    migrated_db_session: AsyncSession,
    phase: object,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint, run = await seed_ready_complaint(
        migrated_db_session,
        customer,
        equipment,
    )
    complaint_id = complaint.id
    _set_diagnostic_phase(run, phase)
    await migrated_db_session.commit()
    _, admin_token = await seed_admin(migrated_db_session)

    response = await api_client.post(
        f"/api/v1/admin/complaints/{complaint.id}/work-orders",
        headers=bearer(admin_token),
        json=WORK_ORDER_PAYLOAD,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "diagnostic_not_ready"
    await migrated_db_session.rollback()
    migrated_db_session.expire_all()

    refreshed = await migrated_db_session.get(type(complaint), complaint_id)
    assert refreshed is not None
    assert refreshed.status is ComplaintStatus.READY_FOR_WORK_ORDER

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
    converted_history_count = await migrated_db_session.scalar(
        select(func.count(ComplaintHistory.id)).where(
            ComplaintHistory.complaint_id == complaint_id,
            ComplaintHistory.event_type == "converted",
        )
    )
    assert converted_history_count == 0


@pytest.mark.asyncio
async def test_direct_conversion_honors_legacy_readiness_exception(
    api_client,
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    # A pre-cutoff legacy complaint predates lifecycle readiness provenance, so
    # its ready state must be seeded rather than driven through a transition.
    complaint = await seed_complaint(
        migrated_db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    _, admin_token = await seed_admin(migrated_db_session)
    settings = get_settings().model_copy(
        update={
            "lifecycle_readiness_enforced_at": datetime.now(UTC)
            + timedelta(days=1),
            "lifecycle_legacy_ready_ids": str(complaint.id),
        }
    )
    monkeypatch.setattr(
        lifecycle_service,
        "get_settings",
        lambda: settings,
    )

    response = await api_client.post(
        f"/api/v1/admin/complaints/{complaint.id}/work-orders",
        headers=bearer(admin_token),
        json=WORK_ORDER_PAYLOAD,
    )

    assert response.status_code == 201, response.text
    converted = await migrated_db_session.scalar(
        select(ComplaintHistory)
        .where(
            ComplaintHistory.complaint_id == complaint.id,
            ComplaintHistory.event_type == "converted",
        )
        .order_by(ComplaintHistory.sequence_number.desc())
        .limit(1)
    )
    assert converted is not None
    assert converted.changed_fields["legacy_readiness_exception"] is True
    assert converted.changed_fields["legacy_readiness_diagnostic"] is None
