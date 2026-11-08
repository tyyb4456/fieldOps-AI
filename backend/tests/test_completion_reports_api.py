from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint
from app.models.customer import Customer
from app.models.equipment import Equipment
from app.models.enums import AssignmentStatus, WorkOrderStatus
from app.models.service_record import ServiceRecord
from app.models.technician import Technician
from app.models.technician_assignment import TechnicianAssignment
from app.models.user import User
from app.models.work_order import WorkOrder
from tests.support import (
    bearer,
    seed_admin,
    seed_complaint,
    seed_customer,
    seed_equipment,
    seed_technician,
)


@dataclass
class CompletionContext:
    customer: Customer
    customer_token: str
    equipment: Equipment
    complaint: Complaint
    admin: User
    admin_token: str
    technician_user: User
    technician: Technician
    technician_token: str
    work_order: WorkOrder
    service_record: ServiceRecord | None


async def _seed_context(
    session: AsyncSession,
    *,
    work_order_status: WorkOrderStatus = WorkOrderStatus.IN_PROGRESS,
    assignment_status: AssignmentStatus = AssignmentStatus.ACCEPTED,
    work_performed: str | None = "Replaced the failed DC connector.",
    with_service_record: bool = True,
) -> CompletionContext:
    _, customer, customer_token = await seed_customer(session)
    equipment = await seed_equipment(session, customer)
    complaint = await seed_complaint(
        session,
        customer,
        equipment=equipment,
    )
    admin, admin_token = await seed_admin(session)
    technician_user, technician, technician_token = await seed_technician(
        session
    )

    work_order = WorkOrder(
        complaint_id=complaint.id,
        equipment_id=equipment.id,
        title="Inspect inverter error E-05",
        description="Reproduce the reported error and inspect DC inputs.",
        status=work_order_status,
    )
    session.add(work_order)
    await session.flush()

    assignment = TechnicianAssignment(
        work_order_id=work_order.id,
        technician_id=technician.id,
        assignment_status=assignment_status,
    )
    session.add(assignment)

    service_record: ServiceRecord | None = None
    if with_service_record:
        service_record = ServiceRecord(
            equipment_id=equipment.id,
            work_order_id=work_order.id,
            technician_id=technician.id,
            findings="Error E-05 reproduced at the DC input.",
            work_performed=work_performed,
        )
        session.add(service_record)

    await session.commit()
    await session.refresh(work_order)
    if service_record is not None:
        await session.refresh(service_record)

    return CompletionContext(
        customer=customer,
        customer_token=customer_token,
        equipment=equipment,
        complaint=complaint,
        admin=admin,
        admin_token=admin_token,
        technician_user=technician_user,
        technician=technician,
        technician_token=technician_token,
        work_order=work_order,
        service_record=service_record,
    )


async def _create_report(
    api_client: Any,
    context: CompletionContext,
    token: str,
    *,
    summary: str = "Inverter generation restored and verified.",
) -> Any:
    assert context.service_record is not None
    return await api_client.post(
        f"/api/v1/work-orders/{context.work_order.id}/completion-reports",
        headers=bearer(token),
        json={
            "service_record_id": str(context.service_record.id),
            "summary": summary,
        },
    )


async def test_completion_report_endpoints_require_authentication(
    api_client: Any,
) -> None:
    response = await api_client.get("/api/v1/completion-reports")

    assert response.status_code == 401


async def test_admin_creates_pending_completion_report(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(migrated_db_session)

    response = await _create_report(
        api_client,
        context,
        context.admin_token,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["work_order_id"] == str(context.work_order.id)
    assert body["service_record_id"] == str(context.service_record.id)
    assert body["evidence_status"] == "pending"
    assert body["verified_at"] is None
    assert body["summary"] == "Inverter generation restored and verified."


async def test_technician_creates_report_with_accepted_assignment(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(migrated_db_session)

    response = await _create_report(
        api_client,
        context,
        context.technician_token,
    )

    assert response.status_code == 201, response.text
    assert response.json()["work_order_id"] == str(context.work_order.id)


async def test_technician_requires_accepted_assignment(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(
        migrated_db_session,
        assignment_status=AssignmentStatus.OFFERED,
    )

    response = await _create_report(
        api_client,
        context,
        context.technician_token,
    )

    assert response.status_code == 404


async def test_customer_cannot_create_completion_report(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(migrated_db_session)

    response = await _create_report(
        api_client,
        context,
        context.customer_token,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_completion_report_rejects_duplicate_work_order(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(migrated_db_session)
    first = await _create_report(
        api_client,
        context,
        context.admin_token,
    )
    assert first.status_code == 201, first.text

    duplicate = await _create_report(
        api_client,
        context,
        context.admin_token,
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "completion_report_conflict"


async def test_completion_report_rejects_foreign_service_record(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(migrated_db_session)
    other_context = await _seed_context(migrated_db_session)
    assert other_context.service_record is not None

    response = await api_client.post(
        f"/api/v1/work-orders/{context.work_order.id}/completion-reports",
        headers=bearer(context.admin_token),
        json={
            "service_record_id": str(other_context.service_record.id),
            "summary": "Attempted cross-work-order association.",
        },
    )

    assert response.status_code == 409
    assert (
        response.json()["error"]["code"]
        == "invalid_completion_report_association"
    )


async def test_completion_report_requires_documented_work(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(
        migrated_db_session,
        work_performed="   ",
    )

    response = await _create_report(
        api_client,
        context,
        context.admin_token,
    )

    assert response.status_code == 409
    assert (
        response.json()["error"]["code"]
        == "invalid_completion_report_state"
    )


async def test_completion_report_requires_reportable_work_order_state(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(
        migrated_db_session,
        work_order_status=WorkOrderStatus.DRAFT,
    )

    response = await _create_report(
        api_client,
        context,
        context.admin_token,
    )

    assert response.status_code == 409
    assert (
        response.json()["error"]["code"]
        == "invalid_completion_report_state"
    )


async def test_completion_report_unknown_work_order_returns_not_found(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(migrated_db_session)
    assert context.service_record is not None
    missing_id = "00000000-0000-0000-0000-000000000000"

    response = await api_client.post(
        f"/api/v1/work-orders/{missing_id}/completion-reports",
        headers=bearer(context.admin_token),
        json={
            "service_record_id": str(context.service_record.id),
            "summary": "Report for a missing work order.",
        },
    )

    assert response.status_code == 404


async def test_admin_verifies_report_and_it_becomes_immutable(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(migrated_db_session)
    created = await _create_report(
        api_client,
        context,
        context.admin_token,
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    verified = await api_client.patch(
        f"/api/v1/completion-reports/{report_id}",
        headers=bearer(context.admin_token),
        json={
            "evidence_status": "verified",
            "verification_notes": "Photo evidence matches the work log.",
        },
    )

    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["evidence_status"] == "verified"
    assert body["verified_at"] is not None
    assert body["verification_notes"] == (
        "Photo evidence matches the work log."
    )

    immutable = await api_client.patch(
        f"/api/v1/completion-reports/{report_id}",
        headers=bearer(context.admin_token),
        json={"summary": "Late edit after verification."},
    )

    assert immutable.status_code == 409
    assert (
        immutable.json()["error"]["code"]
        == "invalid_completion_report_state"
    )


async def test_admin_rejects_then_reopens_report(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(migrated_db_session)
    created = await _create_report(
        api_client,
        context,
        context.admin_token,
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    rejected = await api_client.patch(
        f"/api/v1/completion-reports/{report_id}",
        headers=bearer(context.admin_token),
        json={
            "evidence_status": "rejected",
            "verification_notes": "Evidence is unreadable.",
        },
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["evidence_status"] == "rejected"
    assert rejected.json()["verified_at"] is None

    technician_edit = await api_client.patch(
        f"/api/v1/completion-reports/{report_id}",
        headers=bearer(context.technician_token),
        json={"summary": "Technician tries to fix a rejected report."},
    )
    assert technician_edit.status_code == 409

    reopened = await api_client.patch(
        f"/api/v1/completion-reports/{report_id}",
        headers=bearer(context.admin_token),
        json={"evidence_status": "pending"},
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["evidence_status"] == "pending"
    assert reopened.json()["verified_at"] is None


async def test_admin_cannot_apply_same_evidence_status(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(migrated_db_session)
    created = await _create_report(
        api_client,
        context,
        context.admin_token,
    )
    assert created.status_code == 201, created.text

    response = await api_client.patch(
        f"/api/v1/completion-reports/{created.json()['id']}",
        headers=bearer(context.admin_token),
        json={"evidence_status": "pending"},
    )

    assert response.status_code == 409


async def test_technician_edits_pending_summary_but_not_verification(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(migrated_db_session)
    created = await _create_report(
        api_client,
        context,
        context.technician_token,
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    updated = await api_client.patch(
        f"/api/v1/completion-reports/{report_id}",
        headers=bearer(context.technician_token),
        json={"summary": "Updated summary with final readings."},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["summary"] == (
        "Updated summary with final readings."
    )

    forbidden = await api_client.patch(
        f"/api/v1/completion-reports/{report_id}",
        headers=bearer(context.technician_token),
        json={"evidence_status": "verified"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "forbidden"

    other_technician_user, _, other_token = await seed_technician(
        migrated_db_session
    )
    assert other_technician_user.is_active

    inaccessible = await api_client.patch(
        f"/api/v1/completion-reports/{report_id}",
        headers=bearer(other_token),
        json={"summary": "Another technician edit."},
    )
    assert inaccessible.status_code == 404


async def test_completion_report_lists_are_scoped_and_filterable(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(migrated_db_session)
    other_context = await _seed_context(migrated_db_session)
    assert context.service_record is not None
    assert other_context.service_record is not None

    first = await _create_report(
        api_client,
        context,
        context.admin_token,
    )
    assert first.status_code == 201, first.text
    second = await _create_report(
        api_client,
        other_context,
        other_context.admin_token,
    )
    assert second.status_code == 201, second.text

    admin_list = await api_client.get(
        "/api/v1/admin/completion-reports",
        headers=bearer(context.admin_token),
    )
    assert admin_list.status_code == 200
    assert admin_list.json()["total"] == 2

    by_work_order = await api_client.get(
        "/api/v1/completion-reports",
        headers=bearer(context.admin_token),
        params={"work_order_id": str(context.work_order.id)},
    )
    assert by_work_order.status_code == 200
    assert by_work_order.json()["total"] == 1
    assert by_work_order.json()["items"][0]["id"] == first.json()["id"]

    by_service_record = await api_client.get(
        "/api/v1/completion-reports",
        headers=bearer(context.admin_token),
        params={"service_record_id": str(other_context.service_record.id)},
    )
    assert by_service_record.status_code == 200
    assert by_service_record.json()["total"] == 1
    assert by_service_record.json()["items"][0]["id"] == second.json()["id"]

    customer_list = await api_client.get(
        "/api/v1/completion-reports",
        headers=bearer(context.customer_token),
    )
    assert customer_list.status_code == 200
    assert customer_list.json()["total"] == 1
    assert customer_list.json()["items"][0]["id"] == first.json()["id"]

    technician_list = await api_client.get(
        "/api/v1/completion-reports",
        headers=bearer(context.technician_token),
    )
    assert technician_list.status_code == 200
    assert technician_list.json()["total"] == 1
    assert technician_list.json()["items"][0]["id"] == first.json()["id"]

    paged = await api_client.get(
        "/api/v1/completion-reports",
        headers=bearer(context.admin_token),
        params={"limit": 1, "offset": 0},
    )
    assert paged.status_code == 200
    assert paged.json()["total"] == 2
    assert len(paged.json()["items"]) == 1

    work_order_scope = await api_client.get(
        f"/api/v1/work-orders/{context.work_order.id}/completion-reports",
        headers=bearer(context.customer_token),
    )
    assert work_order_scope.status_code == 200
    assert work_order_scope.json()["total"] == 1

    hidden = await api_client.get(
        f"/api/v1/work-orders/{other_context.work_order.id}/completion-reports",
        headers=bearer(context.customer_token),
    )
    assert hidden.status_code == 404


async def test_completion_report_validation_rejects_unknown_fields(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    context = await _seed_context(migrated_db_session)
    assert context.service_record is not None

    response = await api_client.post(
        f"/api/v1/work-orders/{context.work_order.id}/completion-reports",
        headers=bearer(context.admin_token),
        json={
            "service_record_id": str(context.service_record.id),
            "summary": "Valid summary.",
            "evidence_status": "verified",
        },
    )

    assert response.status_code == 422

    created = await _create_report(
        api_client,
        context,
        context.admin_token,
    )
    assert created.status_code == 201, created.text

    empty_update = await api_client.patch(
        f"/api/v1/completion-reports/{created.json()['id']}",
        headers=bearer(context.admin_token),
        json={},
    )
    assert empty_update.status_code == 422

    null_summary = await api_client.patch(
        f"/api/v1/completion-reports/{created.json()['id']}",
        headers=bearer(context.admin_token),
        json={"summary": None},
    )
    assert null_summary.status_code == 422
