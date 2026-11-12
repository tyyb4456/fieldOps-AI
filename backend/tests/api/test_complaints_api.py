from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.complaint import Complaint
from app.models.complaint_history import ComplaintHistory
from app.models.enums import ComplaintStatus
from app.schemas.complaints.complaint import ComplaintUpdate
from app.services.complaints import complaints as complaint_service
from tests.support import (
    bearer,
    seed_admin,
    seed_complaint,
    seed_customer,
    seed_equipment,
    seed_technician,
)


def complaint_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "description": "The inverter stopped generating power this morning.",
        "reported_error_code": "E-05",
        "channel": "web",
    }
    payload.update(overrides)
    return payload


async def test_complaint_endpoints_require_authentication(api_client) -> None:
    response = await api_client.get("/api/v1/customers/me/complaints")

    assert response.status_code == 401


async def test_customer_can_create_complaint_with_own_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)

    response = await api_client.post(
        "/api/v1/customers/me/complaints",
        headers=bearer(token),
        json=complaint_payload(equipment_id=str(equipment.id)),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["customer_id"] == str(customer.id)
    assert body["equipment_id"] == str(equipment.id)
    assert body["status"] == "received"
    assert body["priority"] == "normal"
    assert body["reported_symptoms"] == []
    assert body["reported_error_code"] == "E-05"


async def test_complaint_can_be_created_without_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)

    response = await api_client.post(
        "/api/v1/customers/me/complaints",
        headers=bearer(token),
        json=complaint_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["customer_id"] == str(customer.id)
    assert body["equipment_id"] is None


async def test_web_submission_cannot_spoof_complaint_channel(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.post(
        "/api/v1/customers/me/complaints",
        headers=bearer(token),
        json=complaint_payload(channel="whatsapp"),
    )

    assert response.status_code == 201
    assert response.json()["channel"] == "web"


async def test_customer_cannot_spoof_complaint_ownership(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)
    _, other_customer, _ = await seed_customer(migrated_db_session)

    response = await api_client.post(
        "/api/v1/customers/me/complaints",
        headers=bearer(token),
        json=complaint_payload(customer_id=str(other_customer.id)),
    )

    assert response.status_code == 422


async def test_customer_cannot_set_internal_complaint_fields(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)
    headers = bearer(token)

    for field, value in (
        ("status", "converted"),
        ("priority", "urgent"),
        ("reported_symptoms", ["invented"]),
    ):
        response = await api_client.post(
            "/api/v1/customers/me/complaints",
            headers=headers,
            json=complaint_payload(**{field: value}),
        )
        assert response.status_code == 422, field


async def test_customer_cannot_associate_another_customers_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, other_customer, _ = await seed_customer(migrated_db_session)
    other_equipment = await seed_equipment(
        migrated_db_session,
        other_customer,
    )
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.post(
        "/api/v1/customers/me/complaints",
        headers=bearer(token),
        json=complaint_payload(equipment_id=str(other_equipment.id)),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_customer_cannot_associate_unknown_equipment(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.post(
        "/api/v1/customers/me/complaints",
        headers=bearer(token),
        json=complaint_payload(equipment_id=str(uuid.uuid4())),
    )

    assert response.status_code == 404


async def test_customer_lists_only_own_complaints(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer_a, token_a = await seed_customer(migrated_db_session)
    _, customer_b, _ = await seed_customer(migrated_db_session)
    own = await seed_complaint(migrated_db_session, customer_a)
    await seed_complaint(migrated_db_session, customer_b)

    response = await api_client.get(
        "/api/v1/customers/me/complaints",
        headers=bearer(token_a),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [str(own.id)]


async def test_customer_can_filter_complaints_by_status(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    await seed_complaint(
        migrated_db_session,
        customer,
        status=ComplaintStatus.RECEIVED,
    )
    converted = await seed_complaint(
        migrated_db_session,
        customer,
        status=ComplaintStatus.CONVERTED,
    )

    response = await api_client.get(
        "/api/v1/customers/me/complaints?status=converted",
        headers=bearer(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(converted.id)


async def test_customer_can_read_own_complaint(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(migrated_db_session, customer)

    response = await api_client.get(
        f"/api/v1/customers/me/complaints/{complaint.id}",
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(complaint.id)


async def test_customer_cannot_read_another_customers_complaint(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, other_customer, _ = await seed_customer(migrated_db_session)
    other_complaint = await seed_complaint(
        migrated_db_session,
        other_customer,
    )
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.get(
        f"/api/v1/customers/me/complaints/{other_complaint.id}",
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_customer_can_update_permitted_complaint_fields(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(migrated_db_session, customer)

    response = await api_client.patch(
        f"/api/v1/customers/me/complaints/{complaint.id}",
        headers=bearer(token),
        json={
            "description": "The inverter now shows a different warning.",
            "reported_error_code": "E-09",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["description"].startswith("The inverter now")
    assert body["reported_error_code"] == "E-09"


async def test_customer_cannot_update_complaint_status_or_priority(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(migrated_db_session, customer)
    headers = bearer(token)
    url = f"/api/v1/customers/me/complaints/{complaint.id}"

    for payload in (
        {"status": "converted"},
        {"priority": "urgent"},
        {"customer_id": str(uuid.uuid4())},
        {"equipment_id": str(uuid.uuid4())},
    ):
        response = await api_client.patch(url, headers=headers, json=payload)
        assert response.status_code == 422, payload


async def test_customer_cannot_update_another_customers_complaint(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, other_customer, _ = await seed_customer(migrated_db_session)
    other_complaint = await seed_complaint(
        migrated_db_session,
        other_customer,
    )
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.patch(
        f"/api/v1/customers/me/complaints/{other_complaint.id}",
        headers=bearer(token),
        json={"description": "Attempted cross-customer edit."},
    )

    assert response.status_code == 404


async def test_customer_cannot_update_converted_complaint(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(
        migrated_db_session,
        customer,
        status=ComplaintStatus.CONVERTED,
    )

    response = await api_client.patch(
        f"/api/v1/customers/me/complaints/{complaint.id}",
        headers=bearer(token),
        json={"description": "Late edit attempt."},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status_transition"


async def test_customer_can_cancel_complaint_and_history_is_preserved(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(migrated_db_session, customer)

    response = await api_client.post(
        f"/api/v1/customers/me/complaints/{complaint.id}/cancel",
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    await migrated_db_session.refresh(complaint)
    assert complaint.status is ComplaintStatus.CANCELLED
    count = await migrated_db_session.scalar(
        select(func.count(Complaint.id)).where(
            Complaint.customer_id == customer.id
        )
    )
    assert count == 1


async def test_customer_cannot_cancel_twice(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(migrated_db_session, customer)
    url = f"/api/v1/customers/me/complaints/{complaint.id}/cancel"

    first = await api_client.post(url, headers=bearer(token))
    second = await api_client.post(url, headers=bearer(token))

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "invalid_status_transition"


async def test_customer_cannot_cancel_converted_complaint(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(
        migrated_db_session,
        customer,
        status=ComplaintStatus.CONVERTED,
    )

    response = await api_client.post(
        f"/api/v1/customers/me/complaints/{complaint.id}/cancel",
        headers=bearer(token),
    )

    assert response.status_code == 409


async def test_customer_cannot_cancel_another_customers_complaint(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, other_customer, _ = await seed_customer(migrated_db_session)
    other_complaint = await seed_complaint(
        migrated_db_session,
        other_customer,
    )
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.post(
        f"/api/v1/customers/me/complaints/{other_complaint.id}/cancel",
        headers=bearer(token),
    )

    assert response.status_code == 404


async def test_concurrent_cancellation_is_serialized(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(migrated_db_session, customer)
    url = f"/api/v1/customers/me/complaints/{complaint.id}/cancel"
    headers = bearer(token)

    first, second = await asyncio.gather(
        api_client.post(url, headers=headers),
        api_client.post(url, headers=headers),
    )

    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409]

    await migrated_db_session.refresh(complaint)
    assert complaint.status is ComplaintStatus.CANCELLED


async def _complaint_history(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> list[ComplaintHistory]:
    result = await session.execute(
        select(ComplaintHistory)
        .where(ComplaintHistory.complaint_id == complaint_id)
        .order_by(ComplaintHistory.sequence_number.asc())
    )
    return list(result.scalars().all())


async def _assert_complaint_row_locked(
    session_factory: async_sessionmaker[AsyncSession],
    complaint_id: uuid.UUID,
) -> None:
    """Prove the editor transaction holds the complaint row lock.

    A separate connection tries ``FOR UPDATE NOWAIT`` on the same row. The
    expected ``55P03`` (lock_not_available) error confirms the row is locked
    by another transaction; anything else means the scenario was not set up.
    """
    async with session_factory() as probe:
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
                return
            raise
        finally:
            await probe.rollback()
        raise AssertionError(
            "the PATCH transaction does not hold the complaint row lock"
        )


async def _wait_for_blocked_complaint_lock(
    session: AsyncSession,
    task: asyncio.Task[object],
    *,
    editor_pid: int,
    timeout: float = 10.0,
) -> None:
    """Wait until cancellation is blocked on the complaint row lock.

    The waiter is identified by its PostgreSQL backend, the editor backend
    that blocks it, and the complaint ``FOR UPDATE`` statement (or the tuple
    lock PostgreSQL grants while it waits). This avoids matching unrelated
    lock waits in the same database. A task that finishes or fails before it
    blocks is reported immediately instead of silently timing out.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    snapshot: list[tuple[object, ...]] = []
    while asyncio.get_running_loop().time() < deadline:
        if task.done():
            if task.cancelled():
                raise AssertionError(
                    "cancellation task was cancelled before blocking on the "
                    "complaint row"
                )
            error = task.exception()
            if error is not None:
                raise AssertionError(
                    "cancellation task failed before blocking on the "
                    f"complaint row: {error!r}"
                ) from error
            raise AssertionError(
                "cancellation task finished before blocking on the complaint "
                "row"
            )

        result = await session.execute(
            text(
                "SELECT DISTINCT a.pid, a.state, a.wait_event_type, "
                "a.wait_event, pg_blocking_pids(a.pid) AS blockers, a.query "
                "FROM pg_stat_activity AS a "
                "WHERE a.datname = current_database() "
                "AND a.pid <> pg_backend_pid() "
                "AND a.wait_event_type = 'Lock' "
                "AND :editor_pid = ANY(pg_blocking_pids(a.pid)) "
                "AND ("
                "  (a.query ILIKE '%from complaints%' "
                "   AND a.query ILIKE '%for update%') "
                "  OR EXISTS ("
                "    SELECT 1 FROM pg_locks AS l "
                "    WHERE l.pid = a.pid AND l.granted "
                "    AND l.locktype = 'tuple' "
                "    AND l.relation = 'complaints'::regclass"
                "  )"
                ")"
            ),
            {"editor_pid": editor_pid},
        )
        rows = result.all()
        snapshot = [tuple(row) for row in rows]
        if rows:
            return
        await asyncio.sleep(0.01)

    if task.cancelled():
        task_state = "cancelled"
    elif task.done():
        task_state = f"finished (exception={task.exception()!r})"
    else:
        task_state = "still pending"
    activity = (
        await session.execute(
            text(
                "SELECT pid, state, wait_event_type, wait_event, "
                "pg_blocking_pids(pid) AS blockers, query "
                "FROM pg_stat_activity "
                "WHERE datname = current_database() "
                "AND pid <> pg_backend_pid()"
            )
        )
    ).all()
    raise AssertionError(
        "timed out waiting for cancellation to block on the complaint row; "
        f"task={task_state}, editor_pid={editor_pid}, "
        f"matching_wait={snapshot!r}, "
        f"activity={[tuple(row) for row in activity]!r}"
    )


async def test_complaint_creation_records_initial_history(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    user, _, token = await seed_customer(migrated_db_session)

    response = await api_client.post(
        "/api/v1/customers/me/complaints",
        headers=bearer(token),
        json=complaint_payload(),
    )

    assert response.status_code == 201
    complaint_id = uuid.UUID(response.json()["id"])
    history = await _complaint_history(
        migrated_db_session,
        complaint_id,
    )
    assert [entry.event_type for entry in history] == ["created"]
    assert history[0].from_status is None
    assert history[0].to_status is ComplaintStatus.RECEIVED
    assert history[0].actor_id == user.id


async def test_complaint_update_preserves_original_words_in_history(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    user, customer, token = await seed_customer(migrated_db_session)
    original = "The inverter stopped generating power after sunrise."
    complaint = await seed_complaint(
        migrated_db_session,
        customer,
        description=original,
    )
    revised = "The inverter now trips the breaker at noon."

    response = await api_client.patch(
        f"/api/v1/customers/me/complaints/{complaint.id}",
        headers=bearer(token),
        json={
            "description": revised,
            "reported_error_code": "E-77",
        },
    )

    assert response.status_code == 200
    history = await _complaint_history(
        migrated_db_session,
        complaint.id,
    )
    assert [entry.event_type for entry in history] == ["updated"]
    assert history[0].from_status is ComplaintStatus.RECEIVED
    assert history[0].to_status is ComplaintStatus.RECEIVED
    assert history[0].actor_id == user.id
    assert history[0].changed_fields == {
        "description": {"from": original, "to": revised},
        "reported_error_code": {"from": None, "to": "E-77"},
    }


async def test_complaint_history_records_create_update_and_cancel(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)
    created = await api_client.post(
        "/api/v1/customers/me/complaints",
        headers=bearer(token),
        json=complaint_payload(),
    )
    complaint_id = uuid.UUID(created.json()["id"])

    await api_client.patch(
        f"/api/v1/customers/me/complaints/{complaint_id}",
        headers=bearer(token),
        json={"description": "Updated complaint wording."},
    )
    cancelled = await api_client.post(
        f"/api/v1/customers/me/complaints/{complaint_id}/cancel",
        headers=bearer(token),
    )

    assert cancelled.status_code == 200
    history = await _complaint_history(
        migrated_db_session,
        complaint_id,
    )
    assert [entry.event_type for entry in history] == [
        "created",
        "updated",
        "cancelled",
    ]
    assert history[-1].from_status is ComplaintStatus.RECEIVED
    assert history[-1].to_status is ComplaintStatus.CANCELLED
    assert history[-1].changed_fields == {
        "status": {"from": "received", "to": "cancelled"}
    }


async def test_customer_cannot_update_cancelled_complaint(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(migrated_db_session, customer)

    cancelled = await api_client.post(
        f"/api/v1/customers/me/complaints/{complaint.id}/cancel",
        headers=bearer(token),
    )
    response = await api_client.patch(
        f"/api/v1/customers/me/complaints/{complaint.id}",
        headers=bearer(token),
        json={"description": "Late edit after cancellation."},
    )

    assert cancelled.status_code == 200
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status_transition"
    assert (
        await _complaint_history(migrated_db_session, complaint.id)
    )[0].event_type == "cancelled"


async def test_update_waits_for_concurrent_cancel_and_is_rejected(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(migrated_db_session, customer)
    session_factory = async_sessionmaker(
        bind=migrated_db_session.bind,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as canceller:
        locked = await complaint_service.get_complaint(
            canceller,
            complaint.id,
            for_update=True,
        )
        await complaint_service.cancel_complaint(canceller, locked)

        update_task = asyncio.create_task(
            api_client.patch(
                f"/api/v1/customers/me/complaints/{complaint.id}",
                headers=bearer(token),
                json={"description": "Concurrent edit attempt."},
            )
        )
        await asyncio.sleep(0.2)
        assert not update_task.done()

        await canceller.commit()
        response = await asyncio.wait_for(update_task, timeout=10)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status_transition"

    history = await _complaint_history(
        migrated_db_session,
        complaint.id,
    )
    assert [entry.event_type for entry in history] == ["cancelled"]


async def test_patch_first_then_cancel_preserves_history_order(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    user, _, token = await seed_customer(migrated_db_session)
    created = await api_client.post(
        "/api/v1/customers/me/complaints",
        headers=bearer(token),
        json=complaint_payload(),
    )
    complaint_id = uuid.UUID(created.json()["id"])
    session_factory = async_sessionmaker(
        bind=migrated_db_session.bind,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as editor:
        editor_pid = int(
            await editor.scalar(text("SELECT pg_backend_pid()"))
        )
        locked = await complaint_service.get_complaint(
            editor,
            complaint_id,
            for_update=True,
        )
        await complaint_service.update_complaint(
            editor,
            locked,
            ComplaintUpdate(description="Edited before cancellation."),
            actor_id=user.id,
        )
        await _assert_complaint_row_locked(session_factory, complaint_id)

        cancel_started = asyncio.Event()

        async def request_cancellation():
            cancel_started.set()
            return await api_client.post(
                f"/api/v1/customers/me/complaints/{complaint_id}/cancel",
                headers=bearer(token),
            )

        cancel_task = asyncio.create_task(request_cancellation())
        await asyncio.wait_for(cancel_started.wait(), timeout=5)
        await _wait_for_blocked_complaint_lock(
            migrated_db_session,
            cancel_task,
            editor_pid=editor_pid,
        )
        assert not cancel_task.done()

        await editor.commit()
        cancelled = await asyncio.wait_for(cancel_task, timeout=10)

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    history = await _complaint_history(migrated_db_session, complaint_id)
    assert [entry.event_type for entry in history] == [
        "created",
        "updated",
        "cancelled",
    ]
    assert [entry.sequence_number for entry in history] == [1, 2, 3]


async def test_concurrent_patches_serialize_and_keep_history_consistent(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)
    original = "The inverter stopped generating power this morning."
    created = await api_client.post(
        "/api/v1/customers/me/complaints",
        headers=bearer(token),
        json=complaint_payload(description=original),
    )
    complaint_id = uuid.UUID(created.json()["id"])
    url = f"/api/v1/customers/me/complaints/{complaint_id}"

    first, second = await asyncio.gather(
        api_client.patch(
            url,
            headers=bearer(token),
            json={"description": "First concurrent edit."},
        ),
        api_client.patch(
            url,
            headers=bearer(token),
            json={"description": "Second concurrent edit."},
        ),
    )

    assert first.status_code == 200
    assert second.status_code == 200

    history = await _complaint_history(migrated_db_session, complaint_id)
    assert [entry.event_type for entry in history] == [
        "created",
        "updated",
        "updated",
    ]
    sequence_numbers = [entry.sequence_number for entry in history]
    assert sequence_numbers == [1, 2, 3]
    assert len(set(sequence_numbers)) == len(sequence_numbers)

    first_update, second_update = (
        entry for entry in history if entry.event_type == "updated"
    )
    first_change = first_update.changed_fields["description"]
    second_change = second_update.changed_fields["description"]
    assert first_change["from"] == original
    assert second_change["from"] == first_change["to"]
    assert {
        first_change["to"],
        second_change["to"],
    } == {"First concurrent edit.", "Second concurrent edit."}

    final = await migrated_db_session.get(Complaint, complaint_id)
    await migrated_db_session.refresh(final)
    assert final.description == second_change["to"]


async def test_admin_can_read_complaint_history(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)
    _, admin_token = await seed_admin(migrated_db_session)
    created = await api_client.post(
        "/api/v1/customers/me/complaints",
        headers=bearer(token),
        json=complaint_payload(),
    )
    complaint_id = created.json()["id"]
    await api_client.patch(
        f"/api/v1/customers/me/complaints/{complaint_id}",
        headers=bearer(token),
        json={"description": "Updated complaint wording."},
    )
    await api_client.post(
        f"/api/v1/customers/me/complaints/{complaint_id}/cancel",
        headers=bearer(token),
    )

    response = await api_client.get(
        f"/api/v1/admin/complaints/{complaint_id}/history",
        headers=bearer(admin_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [item["event_type"] for item in body["items"]] == [
        "created",
        "updated",
        "cancelled",
    ]


async def test_customer_can_filter_cancelled_complaints(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    cancelled = await seed_complaint(
        migrated_db_session,
        customer,
        status=ComplaintStatus.CANCELLED,
    )
    await seed_complaint(migrated_db_session, customer)

    response = await api_client.get(
        "/api/v1/customers/me/complaints?status=cancelled",
        headers=bearer(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(cancelled.id)


async def test_technician_cannot_use_customer_complaint_endpoints(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(migrated_db_session, customer)
    _, _, token = await seed_technician(migrated_db_session)
    headers = bearer(token)

    assert (
        await api_client.get(
            "/api/v1/customers/me/complaints",
            headers=headers,
        )
    ).status_code == 403
    assert (
        await api_client.post(
            "/api/v1/customers/me/complaints",
            headers=headers,
            json=complaint_payload(),
        )
    ).status_code == 403
    assert (
        await api_client.get(
            f"/api/v1/customers/me/complaints/{complaint.id}",
            headers=headers,
        )
    ).status_code == 403


async def test_complaint_pagination_does_not_leak_cross_customer_records(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer_a, token_a = await seed_customer(migrated_db_session)
    _, customer_b, _ = await seed_customer(migrated_db_session)
    for _ in range(3):
        await seed_complaint(migrated_db_session, customer_a)
    for _ in range(5):
        await seed_complaint(migrated_db_session, customer_b)

    first_page = await api_client.get(
        "/api/v1/customers/me/complaints?limit=2&offset=0",
        headers=bearer(token_a),
    )
    beyond = await api_client.get(
        "/api/v1/customers/me/complaints?limit=2&offset=4",
        headers=bearer(token_a),
    )

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert len(first_page.json()["items"]) == 2
    assert beyond.status_code == 200
    assert beyond.json()["total"] == 3
    assert beyond.json()["items"] == []


async def test_admin_can_list_and_read_complaints(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer_a, _ = await seed_customer(migrated_db_session)
    _, customer_b, _ = await seed_customer(migrated_db_session)
    complaint_a = await seed_complaint(migrated_db_session, customer_a)
    await seed_complaint(migrated_db_session, customer_b)
    _, admin_token = await seed_admin(migrated_db_session)
    headers = bearer(admin_token)

    listing = await api_client.get(
        "/api/v1/admin/complaints",
        headers=headers,
    )
    detail = await api_client.get(
        f"/api/v1/admin/complaints/{complaint_a.id}",
        headers=headers,
    )
    missing = await api_client.get(
        f"/api/v1/admin/complaints/{uuid.uuid4()}",
        headers=headers,
    )

    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assert detail.status_code == 200
    assert detail.json()["id"] == str(complaint_a.id)
    assert missing.status_code == 404


async def test_customer_cannot_use_admin_complaint_endpoints(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.get(
        "/api/v1/admin/complaints",
        headers=bearer(token),
    )

    assert response.status_code == 403
