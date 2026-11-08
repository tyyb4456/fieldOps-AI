from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    AssignmentStatus,
    ComplaintStatus,
    WorkOrderStatus,
)
from app.models.technician_assignment import TechnicianAssignment
from app.models.work_order import WorkOrder
from tests.support import (
    bearer,
    seed_admin,
    seed_complaint,
    seed_customer,
    seed_equipment,
    seed_technician,
)

WORK_ORDER_PAYLOAD = {
    "title": "Inspect inverter error E-05",
    "description": "Reproduce the reported error and inspect DC inputs.",
    "diagnostic_checklist": [
        {
            "task": "Verify the displayed error code",
            "source_document": "INV-5000-manual",
            "source_page": 42,
        }
    ],
}


async def _seed_ready_complaint(
    session: AsyncSession,
) -> tuple[object, object, str, object, str]:
    _, customer, customer_token = await seed_customer(session)
    equipment = await seed_equipment(session, customer)
    complaint = await seed_complaint(
        session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    admin, admin_token = await seed_admin(session)
    return customer, equipment, customer_token, admin, admin_token


async def _create_work_order(
    api_client,
    complaint_id: uuid.UUID,
    admin_token: str,
    **overrides: object,
) -> dict[str, object]:
    payload = dict(WORK_ORDER_PAYLOAD)
    payload.update(overrides)
    response = await api_client.post(
        f"/api/v1/admin/complaints/{complaint_id}/work-orders",
        headers=bearer(admin_token),
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _assign(
    api_client,
    work_order_id: str,
    technician_id: uuid.UUID,
    admin_token: str,
) -> dict[str, object]:
    response = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/assignments",
        headers=bearer(admin_token),
        json={"technician_id": str(technician_id)},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _validate(
    api_client,
    work_order_id: object,
    admin_token: str,
) -> None:
    response = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/status",
        headers=bearer(admin_token),
        json={"status": "validated"},
    )
    assert response.status_code == 200, response.text


async def test_work_order_endpoints_require_authentication(api_client) -> None:
    response = await api_client.get("/api/v1/work-orders")

    assert response.status_code == 401


async def test_admin_converts_complaint_once(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    (
        customer,
        _,
        customer_token,
        _,
        admin_token,
    ) = await _seed_ready_complaint(migrated_db_session)

    from app.models.complaint import Complaint

    complaint = await migrated_db_session.scalar(
        select(Complaint).where(Complaint.customer_id == customer.id)
    )
    assert complaint is not None
    assert complaint.status is ComplaintStatus.READY_FOR_WORK_ORDER
    body = await _create_work_order(
        api_client,
        complaint.id,
        admin_token,
    )

    assert body["complaint_id"] == str(complaint.id)
    assert body["status"] == "draft"
    assert body["diagnostic_checklist"] == (
        WORK_ORDER_PAYLOAD["diagnostic_checklist"]
    )

    await migrated_db_session.refresh(complaint)
    assert complaint.status is ComplaintStatus.CONVERTED

    duplicate = await api_client.post(
        f"/api/v1/admin/complaints/{complaint.id}/work-orders",
        headers=bearer(admin_token),
        json=WORK_ORDER_PAYLOAD,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "work_order_conflict"

    customer_view = await api_client.get(
        f"/api/v1/work-orders/{body['id']}",
        headers=bearer(customer_token),
    )
    assert customer_view.status_code == 200
    assert customer_view.json()["id"] == body["id"]


async def test_customer_cannot_use_admin_work_order_endpoints(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    (
        _,
        _,
        customer_token,
        _,
        admin_token,
    ) = await _seed_ready_complaint(migrated_db_session)
    from app.models.complaint import Complaint

    complaint = await migrated_db_session.scalar(select(Complaint))
    assert complaint is not None

    response = await api_client.post(
        f"/api/v1/admin/complaints/{complaint.id}/work-orders",
        headers=bearer(customer_token),
        json=WORK_ORDER_PAYLOAD,
    )
    assert response.status_code == 403

    body = await _create_work_order(
        api_client,
        complaint.id,
        admin_token,
    )
    response = await api_client.post(
        f"/api/v1/admin/work-orders/{body['id']}/status",
        headers=bearer(customer_token),
        json={"status": "validated"},
    )
    assert response.status_code == 403


async def test_admin_validates_work_order_and_customer_cannot_edit_it(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    (
        _,
        _,
        customer_token,
        _,
        admin_token,
    ) = await _seed_ready_complaint(migrated_db_session)
    from app.models.complaint import Complaint

    complaint = await migrated_db_session.scalar(select(Complaint))
    assert complaint is not None
    body = await _create_work_order(
        api_client,
        complaint.id,
        admin_token,
    )

    updated = await api_client.patch(
        f"/api/v1/admin/work-orders/{body['id']}",
        headers=bearer(admin_token),
        json={"title": "Updated diagnostic job"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated diagnostic job"

    validated = await api_client.post(
        f"/api/v1/admin/work-orders/{body['id']}/status",
        headers=bearer(admin_token),
        json={"status": "validated"},
    )
    assert validated.status_code == 200
    assert validated.json()["status"] == "validated"

    forbidden_edit = await api_client.patch(
        f"/api/v1/admin/work-orders/{body['id']}",
        headers=bearer(customer_token),
        json={"title": "Customer edit"},
    )
    assert forbidden_edit.status_code == 403


async def test_assignment_accept_service_record_and_completion_flow(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    (
        _,
        _,
        _,
        _,
        admin_token,
    ) = await _seed_ready_complaint(migrated_db_session)
    from app.models.complaint import Complaint

    complaint = await migrated_db_session.scalar(select(Complaint))
    assert complaint is not None
    body = await _create_work_order(
        api_client,
        complaint.id,
        admin_token,
    )
    work_order_id = body["id"]

    validated = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/status",
        headers=bearer(admin_token),
        json={"status": "validated"},
    )
    assert validated.status_code == 200

    _, technician, technician_token = await seed_technician(
        migrated_db_session
    )
    assignment = await _assign(
        api_client,
        work_order_id,
        technician.id,
        admin_token,
    )
    assert assignment["assignment_status"] == "offered"

    duplicate = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/assignments",
        headers=bearer(admin_token),
        json={"technician_id": str(technician.id)},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "assignment_conflict"

    accepted = await api_client.post(
        f"/api/v1/assignments/{assignment['id']}/accept",
        headers=bearer(technician_token),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["assignment_status"] == "accepted"

    in_progress = await api_client.post(
        f"/api/v1/work-orders/{work_order_id}/status",
        headers=bearer(technician_token),
        json={"status": "in_progress"},
    )
    assert in_progress.status_code == 200
    assert in_progress.json()["status"] == "in_progress"

    service_record = await api_client.post(
        f"/api/v1/work-orders/{work_order_id}/service-records",
        headers=bearer(technician_token),
        json={
            "findings": "Error E-05 reproduced at the DC input.",
            "work_performed": "Replaced the failed DC connector.",
            "parts_used": [{"part": "DC connector", "quantity": 1}],
        },
    )
    assert service_record.status_code == 201, service_record.text
    assert service_record.json()["technician_id"] == str(technician.id)

    pending = await api_client.post(
        f"/api/v1/work-orders/{work_order_id}/status",
        headers=bearer(technician_token),
        json={"status": "pending_verification"},
    )
    assert pending.status_code == 200
    assert pending.json()["status"] == "pending_verification"

    completed = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/status",
        headers=bearer(admin_token),
        json={"status": "completed"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"

    immutable = await api_client.patch(
        f"/api/v1/service-records/{service_record.json()['id']}",
        headers=bearer(technician_token),
        json={"work_performed": "Late edit"},
    )
    assert immutable.status_code == 409
    assert (
        immutable.json()["error"]["code"]
        == "invalid_service_record_state"
    )


async def test_rejected_assignment_returns_work_order_to_assignment_pool(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    (
        _,
        _,
        _,
        _,
        admin_token,
    ) = await _seed_ready_complaint(migrated_db_session)
    from app.models.complaint import Complaint

    complaint = await migrated_db_session.scalar(select(Complaint))
    assert complaint is not None
    body = await _create_work_order(
        api_client,
        complaint.id,
        admin_token,
    )
    work_order_id = body["id"]
    await _validate(api_client, work_order_id, admin_token)

    _, first_technician, first_token = await seed_technician(
        migrated_db_session
    )
    assignment = await _assign(
        api_client,
        work_order_id,
        first_technician.id,
        admin_token,
    )

    rejected = await api_client.post(
        f"/api/v1/assignments/{assignment['id']}/reject",
        headers=bearer(first_token),
    )
    assert rejected.status_code == 200
    assert rejected.json()["assignment_status"] == "rejected"

    refreshed = await api_client.get(
        f"/api/v1/admin/work-orders/{work_order_id}",
        headers=bearer(admin_token),
    )
    assert refreshed.json()["status"] == "awaiting_assignment"

    _, second_technician, _ = await seed_technician(migrated_db_session)
    replacement = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/assignments/reassign",
        headers=bearer(admin_token),
        json={"technician_id": str(second_technician.id)},
    )
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()["technician_id"] == str(
        second_technician.id
    )


async def test_technician_cannot_act_on_another_technicians_assignment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    (
        _,
        _,
        _,
        _,
        admin_token,
    ) = await _seed_ready_complaint(migrated_db_session)
    from app.models.complaint import Complaint

    complaint = await migrated_db_session.scalar(select(Complaint))
    assert complaint is not None
    body = await _create_work_order(
        api_client,
        complaint.id,
        admin_token,
    )
    await _validate(api_client, body["id"], admin_token)
    _, assigned_technician, _ = await seed_technician(migrated_db_session)
    assignment = await _assign(
        api_client,
        body["id"],
        assigned_technician.id,
        admin_token,
    )
    _, _, other_token = await seed_technician(migrated_db_session)

    response = await api_client.post(
        f"/api/v1/assignments/{assignment['id']}/accept",
        headers=bearer(other_token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"

    work_order = await api_client.get(
        f"/api/v1/work-orders/{body['id']}",
        headers=bearer(other_token),
    )
    assert work_order.status_code == 404


async def test_assignment_rejects_inactive_technician(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    (
        _,
        _,
        _,
        _,
        admin_token,
    ) = await _seed_ready_complaint(migrated_db_session)
    from app.models.complaint import Complaint

    complaint = await migrated_db_session.scalar(select(Complaint))
    assert complaint is not None
    body = await _create_work_order(
        api_client,
        complaint.id,
        admin_token,
    )
    await _validate(api_client, body["id"], admin_token)
    _, technician, _ = await seed_technician(
        migrated_db_session,
        is_active=False,
    )

    response = await api_client.post(
        f"/api/v1/admin/work-orders/{body['id']}/assignments",
        headers=bearer(admin_token),
        json={"technician_id": str(technician.id)},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "technician_not_eligible"


async def test_service_record_requires_accepted_assignment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    (
        _,
        _,
        _,
        _,
        admin_token,
    ) = await _seed_ready_complaint(migrated_db_session)
    from app.models.complaint import Complaint

    complaint = await migrated_db_session.scalar(select(Complaint))
    assert complaint is not None
    body = await _create_work_order(
        api_client,
        complaint.id,
        admin_token,
    )
    await _validate(api_client, body["id"], admin_token)
    _, technician, technician_token = await seed_technician(
        migrated_db_session
    )
    await _assign(
        api_client,
        body["id"],
        technician.id,
        admin_token,
    )

    response = await api_client.post(
        f"/api/v1/work-orders/{body['id']}/service-records",
        headers=bearer(technician_token),
        json={"findings": "Attempt before acceptance."},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] in {
        "invalid_service_record_state",
        "assignment_required",
    }


async def test_concurrent_assignment_attempts_create_one_active_assignment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    (
        _,
        _,
        _,
        _,
        admin_token,
    ) = await _seed_ready_complaint(migrated_db_session)
    from app.models.complaint import Complaint

    complaint = await migrated_db_session.scalar(select(Complaint))
    assert complaint is not None
    body = await _create_work_order(
        api_client,
        complaint.id,
        admin_token,
    )
    await _validate(api_client, body["id"], admin_token)
    _, first_technician, _ = await seed_technician(migrated_db_session)
    _, second_technician, _ = await seed_technician(migrated_db_session)

    async def assign(technician_id: uuid.UUID):
        return await api_client.post(
            f"/api/v1/admin/work-orders/{body['id']}/assignments",
            headers=bearer(admin_token),
            json={"technician_id": str(technician_id)},
        )

    first, second = await asyncio.gather(
        assign(first_technician.id),
        assign(second_technician.id),
    )

    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [201, 409]

    active_count = await migrated_db_session.scalar(
        select(func.count(TechnicianAssignment.id)).where(
            TechnicianAssignment.work_order_id == uuid.UUID(body["id"]),
            TechnicianAssignment.assignment_status.in_(
                [
                    AssignmentStatus.OFFERED,
                    AssignmentStatus.ACCEPTED,
                ]
            ),
        )
    )
    assert active_count == 1


async def test_cancelling_work_order_withdraws_active_assignment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    (
        _,
        _,
        _,
        _,
        admin_token,
    ) = await _seed_ready_complaint(migrated_db_session)
    from app.models.complaint import Complaint

    complaint = await migrated_db_session.scalar(select(Complaint))
    assert complaint is not None
    body = await _create_work_order(
        api_client,
        complaint.id,
        admin_token,
    )
    await _validate(api_client, body["id"], admin_token)
    _, technician, technician_token = await seed_technician(
        migrated_db_session
    )
    assignment = await _assign(
        api_client,
        body["id"],
        technician.id,
        admin_token,
    )

    cancelled = await api_client.post(
        f"/api/v1/admin/work-orders/{body['id']}/status",
        headers=bearer(admin_token),
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    assignment_view = await api_client.get(
        f"/api/v1/admin/assignments/{assignment['id']}",
        headers=bearer(admin_token),
    )
    assert assignment_view.status_code == 200
    assert assignment_view.json()["assignment_status"] == "withdrawn"

    hidden = await api_client.get(
        f"/api/v1/work-orders/{body['id']}",
        headers=bearer(technician_token),
    )
    assert hidden.status_code == 404


async def test_concurrent_complaint_conversion_creates_one_work_order(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    (
        _,
        _,
        _,
        _,
        admin_token,
    ) = await _seed_ready_complaint(migrated_db_session)
    from app.models.complaint import Complaint

    complaint = await migrated_db_session.scalar(select(Complaint))
    assert complaint is not None

    async def convert():
        return await api_client.post(
            f"/api/v1/admin/complaints/{complaint.id}/work-orders",
            headers=bearer(admin_token),
            json=WORK_ORDER_PAYLOAD,
        )

    first, second = await asyncio.gather(convert(), convert())
    assert sorted([first.status_code, second.status_code]) == [201, 409]

    work_order_count = await migrated_db_session.scalar(
        select(func.count())
        .select_from(WorkOrder)
        .where(WorkOrder.complaint_id == complaint.id)
    )
    assert work_order_count == 1


async def test_active_assignment_partial_unique_index_is_enforced(
    migrated_db_session: AsyncSession,
) -> None:
    (
        customer,
        _,
        _,
        _,
        _,
    ) = await _seed_ready_complaint(migrated_db_session)
    from app.models.complaint import Complaint
    from app.models.technician import Technician

    complaint = await migrated_db_session.scalar(
        select(Complaint).where(Complaint.customer_id == customer.id)
    )
    assert complaint is not None
    await seed_technician(migrated_db_session)
    await seed_technician(migrated_db_session)
    work_order = WorkOrder(
        complaint_id=complaint.id,
        equipment_id=complaint.equipment_id,
        title="Index test",
        description="Index test",
        status=WorkOrderStatus.VALIDATED,
    )
    migrated_db_session.add(work_order)
    await migrated_db_session.flush()

    technicians = (
        await migrated_db_session.scalars(select(Technician))
    ).all()
    assert len(technicians) >= 2
    migrated_db_session.add_all(
        [
            TechnicianAssignment(
                work_order_id=work_order.id,
                technician_id=technicians[0].id,
                assignment_status=AssignmentStatus.OFFERED,
            ),
            TechnicianAssignment(
                work_order_id=work_order.id,
                technician_id=technicians[1].id,
                assignment_status=AssignmentStatus.ACCEPTED,
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        await migrated_db_session.flush()

    await migrated_db_session.rollback()

    index_names = {
        row[0]
        for row in (
            await migrated_db_session.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'technician_assignments'"
                )
            )
        ).all()
    }
    assert "uq_technician_assignments_active_work_order" in index_names
