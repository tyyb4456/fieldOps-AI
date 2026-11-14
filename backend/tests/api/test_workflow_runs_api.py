from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint
from app.models.enums import ComplaintStatus
from tests.support import (
    bearer,
    seed_admin,
    seed_complaint,
    seed_customer,
    seed_equipment,
    seed_technician,
)


async def _seed_complaint_context(
    session: AsyncSession,
) -> tuple[Complaint, str]:
    _, customer, _ = await seed_customer(session)
    equipment = await seed_equipment(session, customer)
    complaint = await seed_complaint(
        session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.ANALYZING,
    )
    _, admin_token = await seed_admin(session)
    return complaint, admin_token


async def _create_run(
    api_client: Any,
    complaint_id: object,
    admin_token: str,
    *,
    current_step: str | None = "diagnose",
) -> Any:
    return await api_client.post(
        f"/api/v1/admin/complaints/{complaint_id}/workflow-runs",
        headers=bearer(admin_token),
        json={"current_step": current_step},
    )


async def _transition(
    api_client: Any,
    workflow_run_id: str,
    admin_token: str,
    payload: dict[str, object],
) -> Any:
    return await api_client.post(
        f"/api/v1/admin/workflow-runs/{workflow_run_id}/status",
        headers=bearer(admin_token),
        json=payload,
    )


async def test_workflow_run_endpoints_require_authentication(
    api_client: Any,
) -> None:
    response = await api_client.get("/api/v1/admin/workflow-runs")

    assert response.status_code == 401


async def test_workflow_run_endpoints_are_admin_only(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    complaint, _ = await _seed_complaint_context(migrated_db_session)
    _, _, customer_token = await seed_customer(migrated_db_session)
    _, _, technician_token = await seed_technician(migrated_db_session)

    for token in (customer_token, technician_token):
        response = await api_client.post(
            f"/api/v1/admin/complaints/{complaint.id}/workflow-runs",
            headers=bearer(token),
            json={"current_step": "diagnose"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"


async def test_admin_creates_running_workflow_run(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    complaint, admin_token = await _seed_complaint_context(
        migrated_db_session
    )

    response = await _create_run(
        api_client,
        complaint.id,
        admin_token,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["complaint_id"] == str(complaint.id)
    assert body["status"] == "running"
    assert body["current_step"] == "diagnose"
    assert body["started_at"] is not None
    assert body["finished_at"] is None
    assert body["error_message"] is None


async def test_workflow_run_for_unknown_complaint_returns_not_found(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await _seed_complaint_context(migrated_db_session)

    response = await _create_run(
        api_client,
        "00000000-0000-0000-0000-000000000000",
        admin_token,
    )

    assert response.status_code == 404


async def test_workflow_run_pause_resume_and_complete(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    complaint, admin_token = await _seed_complaint_context(
        migrated_db_session
    )
    created = await _create_run(api_client, complaint.id, admin_token)
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]

    paused = await _transition(
        api_client,
        run_id,
        admin_token,
        {"status": "paused", "current_step": "awaiting_customer"},
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"
    assert paused.json()["current_step"] == "awaiting_customer"
    assert paused.json()["finished_at"] is None

    resumed = await _transition(
        api_client,
        run_id,
        admin_token,
        {"status": "running", "current_step": "repair"},
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "running"
    assert resumed.json()["current_step"] == "repair"

    completed = await _transition(
        api_client,
        run_id,
        admin_token,
        {"status": "completed"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["finished_at"] is not None
    assert completed.json()["error_message"] is None

    terminal = await _transition(
        api_client,
        run_id,
        admin_token,
        {"status": "paused"},
    )
    assert terminal.status_code == 409
    assert terminal.json()["error"]["code"] == "invalid_workflow_run_state"


async def test_workflow_run_failure_records_error_message(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    complaint, admin_token = await _seed_complaint_context(
        migrated_db_session
    )
    created = await _create_run(api_client, complaint.id, admin_token)
    assert created.status_code == 201, created.text

    failed = await _transition(
        api_client,
        created.json()["id"],
        admin_token,
        {
            "status": "failed",
            "error_message": "Diagnostic tool timed out.",
        },
    )
    assert failed.status_code == 200, failed.text
    assert failed.json()["status"] == "failed"
    assert failed.json()["finished_at"] is not None
    assert failed.json()["error_message"] == "Diagnostic tool timed out."


async def test_workflow_run_rejects_same_or_invalid_transitions(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    complaint, admin_token = await _seed_complaint_context(
        migrated_db_session
    )
    created = await _create_run(api_client, complaint.id, admin_token)
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]

    same = await _transition(
        api_client,
        run_id,
        admin_token,
        {"status": "running"},
    )
    assert same.status_code == 409

    invalid_error = await _transition(
        api_client,
        run_id,
        admin_token,
        {"status": "paused", "error_message": "Not a failure."},
    )
    assert invalid_error.status_code == 422

    completed = await _transition(
        api_client,
        run_id,
        admin_token,
        {"status": "completed"},
    )
    assert completed.status_code == 200

    failed_after_terminal = await _transition(
        api_client,
        run_id,
        admin_token,
        {"status": "failed", "error_message": "Late failure."},
    )
    assert failed_after_terminal.status_code == 409

    missing = await _transition(
        api_client,
        "00000000-0000-0000-0000-000000000000",
        admin_token,
        {"status": "paused"},
    )
    assert missing.status_code == 404


async def test_workflow_run_lists_are_filterable(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    complaint, admin_token = await _seed_complaint_context(
        migrated_db_session
    )
    other_complaint, _ = await _seed_complaint_context(migrated_db_session)

    first = await _create_run(api_client, complaint.id, admin_token)
    assert first.status_code == 201, first.text
    second = await _create_run(
        api_client,
        complaint.id,
        admin_token,
        current_step="repair",
    )
    assert second.status_code == 201, second.text
    other = await _create_run(api_client, other_complaint.id, admin_token)
    assert other.status_code == 201, other.text

    paused = await _transition(
        api_client,
        second.json()["id"],
        admin_token,
        {"status": "paused"},
    )
    assert paused.status_code == 200

    all_runs = await api_client.get(
        "/api/v1/admin/workflow-runs",
        headers=bearer(admin_token),
    )
    assert all_runs.status_code == 200
    assert all_runs.json()["total"] == 3

    by_complaint = await api_client.get(
        "/api/v1/admin/workflow-runs",
        headers=bearer(admin_token),
        params={"complaint_id": str(complaint.id)},
    )
    assert by_complaint.status_code == 200
    assert by_complaint.json()["total"] == 2

    by_status = await api_client.get(
        "/api/v1/admin/workflow-runs",
        headers=bearer(admin_token),
        params={"status": "paused"},
    )
    assert by_status.status_code == 200
    assert by_status.json()["total"] == 1
    assert by_status.json()["items"][0]["id"] == second.json()["id"]

    complaint_history = await api_client.get(
        f"/api/v1/admin/complaints/{complaint.id}/workflow-runs",
        headers=bearer(admin_token),
    )
    assert complaint_history.status_code == 200
    assert complaint_history.json()["total"] == 2

    paged = await api_client.get(
        f"/api/v1/admin/complaints/{complaint.id}/workflow-runs",
        headers=bearer(admin_token),
        params={"limit": 1, "offset": 1},
    )
    assert paged.status_code == 200
    assert paged.json()["total"] == 2
    assert len(paged.json()["items"]) == 1

    missing_complaint = await api_client.get(
        "/api/v1/admin/complaints/"
        "00000000-0000-0000-0000-000000000000/workflow-runs",
        headers=bearer(admin_token),
    )
    assert missing_complaint.status_code == 404

async def test_workflow_status_reads_are_operations_scoped(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    complaint, admin_token = await _seed_complaint_context(
        migrated_db_session
    )
    created = await _create_run(api_client, complaint.id, admin_token)
    workflow_run_id = created.json()["id"]

    admin_read = await api_client.get(
        f"/api/v1/workflows/{workflow_run_id}",
        headers=bearer(admin_token),
    )
    assert admin_read.status_code == 200, admin_read.text
    assert admin_read.json()["id"] == workflow_run_id

    _, _, customer_token = await seed_customer(migrated_db_session)
    forbidden = await api_client.get(
        f"/api/v1/workflows/{workflow_run_id}",
        headers=bearer(customer_token),
    )
    assert forbidden.status_code == 403

    _, _, technician_token = await seed_technician(migrated_db_session)
    hidden = await api_client.get(
        f"/api/v1/workflows/{workflow_run_id}",
        headers=bearer(technician_token),
    )
    assert hidden.status_code == 404


async def test_workflow_status_unknown_run_returns_not_found(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await _seed_complaint_context(migrated_db_session)

    response = await api_client.get(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000000",
        headers=bearer(admin_token),
    )

    assert response.status_code == 404
