from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.api.routes import assignments as assignment_routes
from app.models.enums import (
    AssignmentStatus,
    ComplaintStatus,
    WorkOrderStatus,
)
from app.models.technician_assignment import TechnicianAssignment
from app.models.user import User
from app.models.work_order import WorkOrder
from app.schemas.assignment import AssignmentCreate
from app.schemas.service_record import ServiceRecordUpdate
from app.services import assignments as assignment_service
from app.services import service_records as service_record_service
from app.services import work_orders as work_order_service
from app.services.assignments import (
    InvalidAssignmentStateError,
    is_active_assignment_conflict,
)
from app.services.service_records import ServiceRecordStateError
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


def _session_factory(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=session.bind,
        expire_on_commit=False,
        autoflush=False,
    )


async def _wait_for_blocked_lock(
    session: AsyncSession,
    *,
    timeout: float = 20.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    snapshot: list[tuple[object, ...]] = []
    while asyncio.get_running_loop().time() < deadline:
        rows = (
            await session.execute(
                text(
                    "SELECT pid, state, wait_event_type, wait_event, query "
                    "FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND pid <> pg_backend_pid()"
                )
            )
        ).all()
        snapshot = [tuple(row) for row in rows]
        if any(row[2] == "Lock" for row in rows):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(
        f"timed out waiting for a blocked row lock: {snapshot}"
    )


async def _create_work_order(
    api_client,
    session: AsyncSession,
    *,
    validate: bool = True,
) -> tuple[str, object, str]:
    _, customer, _ = await seed_customer(session)
    equipment = await seed_equipment(session, customer)
    complaint = await seed_complaint(
        session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    admin, admin_token = await seed_admin(session)
    created = await api_client.post(
        f"/api/v1/admin/complaints/{complaint.id}/work-orders",
        headers=bearer(admin_token),
        json=WORK_ORDER_PAYLOAD,
    )
    assert created.status_code == 201, created.text
    work_order_id = created.json()["id"]

    if validate:
        validated = await api_client.post(
            f"/api/v1/admin/work-orders/{work_order_id}/status",
            headers=bearer(admin_token),
            json={"status": "validated"},
        )
        assert validated.status_code == 200, validated.text

    return work_order_id, admin, admin_token


async def _offer_work_order(
    api_client,
    session: AsyncSession,
    work_order_id: str,
    admin_token: str,
    *,
    full_name: str = "Test Technician",
) -> tuple[object, object, str, dict[str, object]]:
    user, technician, token = await seed_technician(
        session,
        full_name=full_name,
    )
    response = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/assignments",
        headers=bearer(admin_token),
        json={"technician_id": str(technician.id)},
    )
    assert response.status_code == 201, response.text
    return user, technician, token, response.json()


async def _assignment_state(
    session_factory: async_sessionmaker[AsyncSession],
    work_order_id: uuid.UUID,
) -> tuple[WorkOrderStatus, dict[uuid.UUID, AssignmentStatus]]:
    async with session_factory() as session:
        work_order = await session.get(WorkOrder, work_order_id)
        assert work_order is not None
        rows = (
            await session.execute(
                select(TechnicianAssignment).where(
                    TechnicianAssignment.work_order_id == work_order_id
                )
            )
        ).scalars().all()
        return work_order.status, {
            row.id: row.assignment_status for row in rows
        }


async def test_accept_racing_reassignment_returns_conflict(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    work_order_id, _, admin_token = await _create_work_order(
        api_client,
        migrated_db_session,
    )
    technician_user, _, _, assignment = await _offer_work_order(
        api_client,
        migrated_db_session,
        work_order_id,
        admin_token,
    )
    _, replacement_technician, _ = await seed_technician(
        migrated_db_session
    )
    work_order_uuid = uuid.UUID(work_order_id)
    assignment_id = uuid.UUID(assignment["id"])
    session_factory = _session_factory(migrated_db_session)
    accepting_started = asyncio.Event()

    async def competing_accept() -> None:
        async with session_factory() as accept_session:
            accepting_user = await accept_session.scalar(
                select(User)
                .options(selectinload(User.technician))
                .where(User.id == technician_user.id)
            )
            assert accepting_user is not None
            accepting_started.set()
            await assignment_service.accept_assignment(
                accept_session,
                user=accepting_user,
                assignment_id=assignment_id,
            )

    async with session_factory() as reassigner:
        replacement = await assignment_service.create_assignment(
            reassigner,
            work_order_id=work_order_uuid,
            technician_id=replacement_technician.id,
            reassign=True,
        )
        accept_task = asyncio.create_task(competing_accept())
        await accepting_started.wait()
        await _wait_for_blocked_lock(migrated_db_session)
        assert not accept_task.done()

        await reassigner.commit()
        with pytest.raises(InvalidAssignmentStateError):
            await asyncio.wait_for(accept_task, timeout=10)

    status, states = await _assignment_state(
        session_factory,
        work_order_uuid,
    )
    assert status is WorkOrderStatus.ASSIGNED
    assert states[assignment_id] is AssignmentStatus.WITHDRAWN
    assert states[replacement.id] is AssignmentStatus.OFFERED
    assert AssignmentStatus.ACCEPTED not in states.values()


async def test_reject_racing_reassignment_returns_conflict(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    work_order_id, _, admin_token = await _create_work_order(
        api_client,
        migrated_db_session,
    )
    technician_user, _, _, assignment = await _offer_work_order(
        api_client,
        migrated_db_session,
        work_order_id,
        admin_token,
    )
    _, replacement_technician, _ = await seed_technician(
        migrated_db_session
    )
    work_order_uuid = uuid.UUID(work_order_id)
    assignment_id = uuid.UUID(assignment["id"])
    session_factory = _session_factory(migrated_db_session)
    rejecting_started = asyncio.Event()

    async def competing_reject() -> None:
        async with session_factory() as reject_session:
            rejecting_user = await reject_session.scalar(
                select(User)
                .options(selectinload(User.technician))
                .where(User.id == technician_user.id)
            )
            assert rejecting_user is not None
            rejecting_started.set()
            await assignment_service.reject_assignment(
                reject_session,
                user=rejecting_user,
                assignment_id=assignment_id,
            )

    async with session_factory() as reassigner:
        replacement = await assignment_service.create_assignment(
            reassigner,
            work_order_id=work_order_uuid,
            technician_id=replacement_technician.id,
            reassign=True,
        )
        reject_task = asyncio.create_task(competing_reject())
        await rejecting_started.wait()
        await _wait_for_blocked_lock(migrated_db_session)
        assert not reject_task.done()

        await reassigner.commit()
        with pytest.raises(InvalidAssignmentStateError):
            await asyncio.wait_for(reject_task, timeout=10)

    status, states = await _assignment_state(
        session_factory,
        work_order_uuid,
    )
    assert status is WorkOrderStatus.ASSIGNED
    assert states[assignment_id] is AssignmentStatus.WITHDRAWN
    assert states[replacement.id] is AssignmentStatus.OFFERED
    assert AssignmentStatus.REJECTED not in states.values()


async def test_withdrawn_assignment_cannot_be_accepted_and_pool_reaccepts(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    work_order_id, _, admin_token = await _create_work_order(
        api_client,
        migrated_db_session,
    )
    _, _, technician_token, assignment = await _offer_work_order(
        api_client,
        migrated_db_session,
        work_order_id,
        admin_token,
    )
    work_order_uuid = uuid.UUID(work_order_id)
    assignment_id = uuid.UUID(assignment["id"])

    withdrawn = await api_client.post(
        f"/api/v1/admin/assignments/{assignment_id}/withdraw",
        headers=bearer(admin_token),
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["assignment_status"] == "withdrawn"

    rejected_accept = await api_client.post(
        f"/api/v1/assignments/{assignment_id}/accept",
        headers=bearer(technician_token),
    )
    assert rejected_accept.status_code == 409
    assert (
        rejected_accept.json()["error"]["code"]
        == "invalid_assignment_state"
    )

    session_factory = _session_factory(migrated_db_session)
    status, states = await _assignment_state(
        session_factory,
        work_order_uuid,
    )
    assert status is WorkOrderStatus.AWAITING_ASSIGNMENT
    assert states[assignment_id] is AssignmentStatus.WITHDRAWN

    new_user, new_technician, _ = await seed_technician(
        migrated_db_session
    )
    replacement = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/assignments",
        headers=bearer(admin_token),
        json={"technician_id": str(new_technician.id)},
    )
    assert replacement.status_code == 201, replacement.text

    status, states = await _assignment_state(
        session_factory,
        work_order_uuid,
    )
    assert status is WorkOrderStatus.ASSIGNED
    assert states[assignment_id] is AssignmentStatus.WITHDRAWN
    assert states[uuid.UUID(replacement.json()["id"])] is (
        AssignmentStatus.OFFERED
    )


async def test_stale_assignment_refreshes_after_work_order_lock(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    work_order_id, admin, admin_token = await _create_work_order(
        api_client,
        migrated_db_session,
    )
    user, _, _, assignment = await _offer_work_order(
        api_client,
        migrated_db_session,
        work_order_id,
        admin_token,
    )
    assignment_id = uuid.UUID(assignment["id"])
    session_factory = _session_factory(migrated_db_session)

    async with session_factory() as stale_session:
        stale_user = await stale_session.scalar(
            select(User)
            .options(selectinload(User.technician))
            .where(User.id == user.id)
        )
        assert stale_user is not None
        stale_assignment = await assignment_service.get_assignment_for_user(
            stale_session,
            stale_user,
            assignment_id,
        )
        assert stale_assignment.assignment_status is AssignmentStatus.OFFERED

        async with session_factory() as withdrawer:
            withdrawing_admin = await withdrawer.get(User, admin.id)
            assert withdrawing_admin is not None
            await assignment_service.withdraw_assignment(
                withdrawer,
                user=withdrawing_admin,
                assignment_id=assignment_id,
            )
            await withdrawer.commit()

        assert (
            stale_assignment.assignment_status is AssignmentStatus.OFFERED
        )

        with pytest.raises(InvalidAssignmentStateError):
            await assignment_service.accept_assignment(
                stale_session,
                user=stale_user,
                assignment_id=assignment_id,
            )

        assert (
            stale_assignment.assignment_status
            is AssignmentStatus.WITHDRAWN
        )
        await stale_session.rollback()


async def test_returning_offered_escalated_work_order_withdraws_offer(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    work_order_id, _, admin_token = await _create_work_order(
        api_client,
        migrated_db_session,
    )
    _, _, _, assignment = await _offer_work_order(
        api_client,
        migrated_db_session,
        work_order_id,
        admin_token,
    )
    assignment_id = uuid.UUID(assignment["id"])
    session_factory = _session_factory(migrated_db_session)

    escalated = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/status",
        headers=bearer(admin_token),
        json={"status": "escalated"},
    )
    assert escalated.status_code == 200, escalated.text
    assert escalated.json()["status"] == "escalated"

    retained = await api_client.get(
        f"/api/v1/admin/assignments/{assignment_id}",
        headers=bearer(admin_token),
    )
    assert retained.json()["assignment_status"] == "offered"

    returned = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/status",
        headers=bearer(admin_token),
        json={"status": "awaiting_assignment"},
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "awaiting_assignment"

    status, states = await _assignment_state(
        session_factory,
        uuid.UUID(work_order_id),
    )
    assert status is WorkOrderStatus.AWAITING_ASSIGNMENT
    assert states[assignment_id] is AssignmentStatus.WITHDRAWN

    new_user, new_technician, _ = await seed_technician(
        migrated_db_session
    )
    replacement = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/assignments",
        headers=bearer(admin_token),
        json={"technician_id": str(new_technician.id)},
    )
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()["assignment_status"] == "offered"


async def test_returning_accepted_escalated_work_order_withdraws_assignment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    work_order_id, _, admin_token = await _create_work_order(
        api_client,
        migrated_db_session,
    )
    _, _, technician_token, assignment = await _offer_work_order(
        api_client,
        migrated_db_session,
        work_order_id,
        admin_token,
    )
    assignment_id = uuid.UUID(assignment["id"])
    session_factory = _session_factory(migrated_db_session)

    accepted = await api_client.post(
        f"/api/v1/assignments/{assignment_id}/accept",
        headers=bearer(technician_token),
    )
    assert accepted.status_code == 200, accepted.text

    escalated = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/status",
        headers=bearer(admin_token),
        json={"status": "escalated"},
    )
    assert escalated.status_code == 200, escalated.text

    returned = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/status",
        headers=bearer(admin_token),
        json={"status": "awaiting_assignment"},
    )
    assert returned.status_code == 200, returned.text

    status, states = await _assignment_state(
        session_factory,
        uuid.UUID(work_order_id),
    )
    assert status is WorkOrderStatus.AWAITING_ASSIGNMENT
    assert states[assignment_id] is AssignmentStatus.WITHDRAWN


async def test_returning_in_progress_escalated_work_order_withdraws_assignment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    work_order_id, _, admin_token = await _create_work_order(
        api_client,
        migrated_db_session,
    )
    _, _, technician_token, assignment = await _offer_work_order(
        api_client,
        migrated_db_session,
        work_order_id,
        admin_token,
    )
    assignment_id = uuid.UUID(assignment["id"])
    session_factory = _session_factory(migrated_db_session)

    accepted = await api_client.post(
        f"/api/v1/assignments/{assignment_id}/accept",
        headers=bearer(technician_token),
    )
    assert accepted.status_code == 200, accepted.text

    in_progress = await api_client.post(
        f"/api/v1/work-orders/{work_order_id}/status",
        headers=bearer(technician_token),
        json={"status": "in_progress"},
    )
    assert in_progress.status_code == 200, in_progress.text

    escalated = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/status",
        headers=bearer(admin_token),
        json={"status": "escalated"},
    )
    assert escalated.status_code == 200, escalated.text

    returned = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/status",
        headers=bearer(admin_token),
        json={"status": "awaiting_assignment"},
    )
    assert returned.status_code == 200, returned.text

    status, states = await _assignment_state(
        session_factory,
        uuid.UUID(work_order_id),
    )
    assert status is WorkOrderStatus.AWAITING_ASSIGNMENT
    assert states[assignment_id] is AssignmentStatus.WITHDRAWN


async def test_invalid_escalation_transition_is_rejected(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    work_order_id, _, admin_token = await _create_work_order(
        api_client,
        migrated_db_session,
        validate=False,
    )

    response = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/status",
        headers=bearer(admin_token),
        json={"status": "escalated"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status_transition"


async def test_failed_withdrawal_rolls_back_return_to_pool(
    api_client,
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_order_id, admin, admin_token = await _create_work_order(
        api_client,
        migrated_db_session,
    )
    _, _, _, assignment = await _offer_work_order(
        api_client,
        migrated_db_session,
        work_order_id,
        admin_token,
    )
    assignment_id = uuid.UUID(assignment["id"])
    session_factory = _session_factory(migrated_db_session)

    escalated = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/status",
        headers=bearer(admin_token),
        json={"status": "escalated"},
    )
    assert escalated.status_code == 200, escalated.text

    async def fail_withdrawal(session, work_order_id) -> None:
        raise RuntimeError("simulated withdrawal failure")

    monkeypatch.setattr(
        work_order_service,
        "_withdraw_active_assignments",
        fail_withdrawal,
    )

    async with session_factory() as transition_session:
        transitioning_admin = await transition_session.get(User, admin.id)
        assert transitioning_admin is not None
        with pytest.raises(RuntimeError):
            await work_order_service.transition_work_order(
                transition_session,
                user=transitioning_admin,
                work_order_id=uuid.UUID(work_order_id),
                target_status=WorkOrderStatus.AWAITING_ASSIGNMENT,
            )
        await transition_session.rollback()

    status, states = await _assignment_state(
        session_factory,
        uuid.UUID(work_order_id),
    )
    assert status is WorkOrderStatus.ESCALATED
    assert states[assignment_id] is AssignmentStatus.OFFERED


async def test_service_record_update_reloads_after_work_order_lock(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    work_order_id, _, admin_token = await _create_work_order(
        api_client,
        migrated_db_session,
    )
    user, _, technician_token, assignment = await _offer_work_order(
        api_client,
        migrated_db_session,
        work_order_id,
        admin_token,
    )
    accepted = await api_client.post(
        f"/api/v1/assignments/{assignment['id']}/accept",
        headers=bearer(technician_token),
    )
    assert accepted.status_code == 200, accepted.text

    created = await api_client.post(
        f"/api/v1/work-orders/{work_order_id}/service-records",
        headers=bearer(technician_token),
        json={"findings": "Initial findings."},
    )
    assert created.status_code == 201, created.text
    service_record_id = uuid.UUID(created.json()["id"])
    session_factory = _session_factory(migrated_db_session)

    async with session_factory() as competing:
        competing_user = await competing.scalar(
            select(User)
            .options(selectinload(User.technician))
            .where(User.id == user.id)
        )
        assert competing_user is not None
        await service_record_service.update_service_record(
            competing,
            user=competing_user,
            service_record_id=service_record_id,
            data=ServiceRecordUpdate(
                findings=None,
                work_performed="Completed by the competing update.",
            ),
        )
        flush_task = asyncio.create_task(
            api_client.patch(
                f"/api/v1/service-records/{service_record_id}",
                headers=bearer(technician_token),
                json={"work_performed": None},
            )
        )
        await _wait_for_blocked_lock(migrated_db_session)
        assert not flush_task.done()

        await competing.commit()
        response = await asyncio.wait_for(flush_task, timeout=10)

    assert response.status_code == 409
    assert (
        response.json()["error"]["code"]
        == "invalid_service_record_state"
    )

    async with session_factory() as verifier:
        record = await service_record_service.get_service_record_for_user(
            verifier,
            await verifier.scalar(
                select(User)
                .options(selectinload(User.technician))
                .where(User.id == user.id)
            ),
            service_record_id,
        )
        assert record.findings is None
        assert record.work_performed == "Completed by the competing update."


async def test_service_record_state_error_on_stale_values(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    work_order_id, _, admin_token = await _create_work_order(
        api_client,
        migrated_db_session,
    )
    user, _, technician_token, assignment = await _offer_work_order(
        api_client,
        migrated_db_session,
        work_order_id,
        admin_token,
    )
    accepted = await api_client.post(
        f"/api/v1/assignments/{assignment['id']}/accept",
        headers=bearer(technician_token),
    )
    assert accepted.status_code == 200, accepted.text
    created = await api_client.post(
        f"/api/v1/work-orders/{work_order_id}/service-records",
        headers=bearer(technician_token),
        json={"findings": "Initial findings."},
    )
    assert created.status_code == 201, created.text
    service_record_id = uuid.UUID(created.json()["id"])
    session_factory = _session_factory(migrated_db_session)

    async with session_factory() as stale_session:
        stale_user = await stale_session.scalar(
            select(User)
            .options(selectinload(User.technician))
            .where(User.id == user.id)
        )
        assert stale_user is not None
        stale_record = (
            await service_record_service.get_service_record_for_user(
                stale_session,
                stale_user,
                service_record_id,
            )
        )
        assert stale_record.findings == "Initial findings."

        async with session_factory() as writer:
            writer_user = await writer.scalar(
                select(User)
                .options(selectinload(User.technician))
                .where(User.id == user.id)
            )
            assert writer_user is not None
            await service_record_service.update_service_record(
                writer,
                user=writer_user,
                service_record_id=service_record_id,
                data=ServiceRecordUpdate(
                    findings=None,
                    work_performed="Completed by the other writer.",
                ),
            )
            await writer.commit()

        with pytest.raises(ServiceRecordStateError):
            await service_record_service.update_service_record(
                stale_session,
                user=stale_user,
                service_record_id=service_record_id,
                data=ServiceRecordUpdate(work_performed=None),
            )

        assert stale_record.findings is None
        await stale_session.rollback()


class _FakeDatabaseError:
    def __init__(self, constraint_name: str) -> None:
        self.constraint_name = constraint_name


def test_active_assignment_conflict_detection_is_specific() -> None:
    matching = IntegrityError(
        "INSERT INTO technician_assignments ...",
        {},
        _FakeDatabaseError(
            "uq_technician_assignments_active_work_order"
        ),
    )
    unrelated = IntegrityError(
        "INSERT INTO technician_assignments ...",
        {},
        _FakeDatabaseError("uq_work_orders_complaint_id"),
    )

    assert is_active_assignment_conflict(matching) is True
    assert is_active_assignment_conflict(unrelated) is False


async def test_unrelated_integrity_error_is_not_reported_as_conflict(
    api_client,
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_order_id, admin, admin_token = await _create_work_order(
        api_client,
        migrated_db_session,
    )
    _, technician, _ = await seed_technician(migrated_db_session)

    async def raise_integrity_error(*args, **kwargs):
        raise IntegrityError(
            "INSERT INTO technician_assignments ...",
            {},
            _FakeDatabaseError("uq_work_orders_complaint_id"),
        )

    monkeypatch.setattr(
        assignment_service,
        "create_assignment",
        raise_integrity_error,
    )

    session_factory = _session_factory(migrated_db_session)
    async with session_factory() as session:
        calling_admin = await session.get(User, admin.id)
        assert calling_admin is not None
        with pytest.raises(IntegrityError):
            await assignment_routes.create_assignment(
                work_order_id=uuid.UUID(work_order_id),
                payload=AssignmentCreate(technician_id=technician.id),
                admin=calling_admin,
                session=session,
            )


async def test_active_assignment_integrity_error_returns_generic_conflict(
    api_client,
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_order_id, _, admin_token = await _create_work_order(
        api_client,
        migrated_db_session,
    )
    _, technician, _ = await seed_technician(migrated_db_session)

    async def raise_integrity_error(*args, **kwargs):
        raise IntegrityError(
            "INSERT INTO technician_assignments ...",
            {},
            _FakeDatabaseError(
                "uq_technician_assignments_active_work_order"
            ),
        )

    monkeypatch.setattr(
        assignment_service,
        "create_assignment",
        raise_integrity_error,
    )

    response = await api_client.post(
        f"/api/v1/admin/work-orders/{work_order_id}/assignments",
        headers=bearer(admin_token),
        json={"technician_id": str(technician.id)},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "assignment_conflict"
    assert "uq_technician_assignments" not in response.text
