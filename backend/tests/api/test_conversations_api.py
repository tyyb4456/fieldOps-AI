from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_task import BackgroundTask
from app.models.complaint import Complaint
from app.models.conversation import Conversation
from app.models.enums import (
    AssignmentStatus,
    ComplaintChannel,
    MessageSenderType,
)
from app.models.message import Message
from app.models.outbox_event import OutboxEvent
from app.models.technician import Technician
from app.models.technician_assignment import TechnicianAssignment
from app.models.work_order import WorkOrder
from app.models.workflow_run import WorkflowRun
from app.services.conversations import conversations as conversation_service
from tests.support import (
    bearer,
    seed_admin,
    seed_complaint,
    seed_conversation,
    seed_customer,
    seed_equipment,
    seed_message,
    seed_technician,
)


def _idempotency_key() -> str:
    return f"test-{uuid.uuid4().hex}"


def _message_headers(token: str, key: str | None = None) -> dict[str, str]:
    headers = bearer(token)
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


async def _seed_owned_conversation(
    session: AsyncSession,
) -> tuple[uuid.UUID, Complaint, Conversation, str]:
    _, customer, token = await seed_customer(session)
    complaint = await seed_complaint(session, customer)
    conversation = await seed_conversation(session, complaint)
    return customer.id, complaint, conversation, token


async def _seed_visibility_assignment(
    session: AsyncSession,
    complaint: Complaint,
    technician: Technician,
    *,
    assignment_status: AssignmentStatus = AssignmentStatus.ACCEPTED,
) -> WorkOrder:
    if complaint.equipment_id is None:
        raise AssertionError("visibility fixture requires complaint equipment")
    work_order = WorkOrder(
        complaint_id=complaint.id,
        equipment_id=complaint.equipment_id,
        title="Inspect the reported inverter issue",
        description="Inspect the equipment and reproduce the reported fault.",
    )
    session.add(work_order)
    await session.flush()
    session.add(
        TechnicianAssignment(
            work_order_id=work_order.id,
            technician_id=technician.id,
            assignment_status=assignment_status,
        )
    )
    await session.commit()
    return work_order


async def _message_count(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(Message.id))) or 0)


async def test_conversation_endpoints_require_authentication(
    api_client: Any,
) -> None:
    conversation_id = uuid.uuid4()
    complaint_id = uuid.uuid4()

    responses = [
        await api_client.get(
            f"/api/v1/customers/me/complaints/{complaint_id}/conversations"
        ),
        await api_client.get(
            f"/api/v1/customers/me/conversations/{conversation_id}/messages"
        ),
        await api_client.post(
            f"/api/v1/customers/me/conversations/{conversation_id}/messages",
            json={"content": "Hello"},
            headers={"Idempotency-Key": _idempotency_key()},
        ),
        await api_client.get("/api/v1/conversations"),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401, 401]


async def test_customer_lists_only_their_complaint_conversations(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(migrated_db_session, customer)
    conversation = await seed_conversation(migrated_db_session, complaint)

    _, other_customer, _ = await seed_customer(migrated_db_session)
    other_complaint = await seed_complaint(
        migrated_db_session,
        other_customer,
    )
    await seed_conversation(migrated_db_session, other_complaint)

    response = await api_client.get(
        f"/api/v1/customers/me/complaints/{complaint.id}/conversations",
        headers=bearer(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [str(conversation.id)]
    assert body["items"][0]["complaint_id"] == str(complaint.id)
    assert body["items"][0]["channel"] == "web"


async def test_customer_cannot_list_another_customers_conversations(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, other_customer, _ = await seed_customer(migrated_db_session)
    other_complaint = await seed_complaint(
        migrated_db_session,
        other_customer,
    )
    await seed_conversation(migrated_db_session, other_complaint)
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.get(
        f"/api/v1/customers/me/complaints/{other_complaint.id}/conversations",
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_customer_cannot_read_another_customers_messages(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, other_customer, _ = await seed_customer(migrated_db_session)
    other_complaint = await seed_complaint(
        migrated_db_session,
        other_customer,
    )
    other_conversation = await seed_conversation(
        migrated_db_session,
        other_complaint,
    )
    await seed_message(migrated_db_session, other_conversation)
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.get(
        f"/api/v1/customers/me/conversations/{other_conversation.id}/messages",
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_customer_cannot_post_to_another_customers_conversation(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, other_customer, _ = await seed_customer(migrated_db_session)
    other_complaint = await seed_complaint(
        migrated_db_session,
        other_customer,
    )
    other_conversation = await seed_conversation(
        migrated_db_session,
        other_complaint,
    )
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.post(
        f"/api/v1/customers/me/conversations/{other_conversation.id}/messages",
        headers=_message_headers(token, _idempotency_key()),
        json={"content": "Unauthorized message."},
    )

    assert response.status_code == 404
    assert await _message_count(migrated_db_session) == 0


async def test_customer_can_read_but_not_post_to_non_web_conversation(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(migrated_db_session, customer)
    conversation = await seed_conversation(
        migrated_db_session,
        complaint,
        channel=ComplaintChannel.WHATSAPP,
    )
    await seed_message(
        migrated_db_session,
        conversation,
        content="Provider-delivered message.",
    )

    history = await api_client.get(
        f"/api/v1/customers/me/conversations/{conversation.id}/messages",
        headers=bearer(token),
    )
    submitted = await api_client.post(
        f"/api/v1/customers/me/conversations/{conversation.id}/messages",
        headers=_message_headers(token, _idempotency_key()),
        json={"content": "Customer reply."},
    )

    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert submitted.status_code == 409
    assert (
        submitted.json()["error"]["code"]
        == "unsupported_conversation_channel"
    )
    assert await _message_count(migrated_db_session) == 1


async def test_staff_can_reply_to_non_web_conversation(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(migrated_db_session, customer)
    conversation = await seed_conversation(
        migrated_db_session,
        complaint,
        channel=ComplaintChannel.WHATSAPP,
    )
    _, admin_token = await seed_admin(migrated_db_session)

    reply = await api_client.post(
        f"/api/v1/conversations/{conversation.id}/messages",
        headers=_message_headers(admin_token, _idempotency_key()),
        json={"content": "Staff reply on external conversation."},
    )

    assert reply.status_code == 201, reply.text
    assert reply.json()["sender_type"] == "staff"


async def test_missing_complaint_and_conversation_return_not_found(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)
    headers = bearer(token)

    missing_complaint = await api_client.get(
        f"/api/v1/customers/me/complaints/{uuid.uuid4()}/conversations",
        headers=headers,
    )
    missing_conversation = await api_client.get(
        f"/api/v1/customers/me/conversations/{uuid.uuid4()}/messages",
        headers=headers,
    )

    assert missing_complaint.status_code == 404
    assert missing_conversation.status_code == 404


async def test_non_customer_roles_cannot_use_customer_message_endpoints(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, complaint, conversation, _ = await _seed_owned_conversation(
        migrated_db_session
    )
    _, _, technician_token = await seed_technician(migrated_db_session)
    _, admin_token = await seed_admin(migrated_db_session)

    for token in (technician_token, admin_token):
        list_response = await api_client.get(
            f"/api/v1/customers/me/complaints/{complaint.id}/conversations",
            headers=bearer(token),
        )
        read_response = await api_client.get(
            f"/api/v1/customers/me/conversations/{conversation.id}/messages",
            headers=bearer(token),
        )
        post_response = await api_client.post(
            f"/api/v1/customers/me/conversations/{conversation.id}/messages",
            headers=_message_headers(token, _idempotency_key()),
            json={"content": "Wrong role."},
        )
        assert list_response.status_code == 403
        assert read_response.status_code == 403
        assert post_response.status_code == 403


async def test_admin_can_list_read_and_reply_to_conversations(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, complaint, conversation, customer_token = (
        await _seed_owned_conversation(migrated_db_session)
    )
    await seed_message(
        migrated_db_session,
        conversation,
        content="Customer question.",
    )
    _, admin_token = await seed_admin(migrated_db_session)
    admin_headers = bearer(admin_token)

    listing = await api_client.get(
        "/api/v1/conversations",
        headers=admin_headers,
        params={"complaint_id": str(complaint.id)},
    )
    messages = await api_client.get(
        f"/api/v1/conversations/{conversation.id}/messages",
        headers=admin_headers,
    )
    reply = await api_client.post(
        f"/api/v1/conversations/{conversation.id}/messages",
        headers=_message_headers(admin_token, _idempotency_key()),
        json={"content": "Staff response."},
    )

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert messages.status_code == 200
    assert messages.json()["total"] == 1
    assert reply.status_code == 201
    assert reply.json()["sender_type"] == "staff"

    customer_view = await api_client.get(
        f"/api/v1/customers/me/conversations/{conversation.id}/messages",
        headers=bearer(customer_token),
    )
    assert customer_view.status_code == 200
    assert [item["sender_type"] for item in customer_view.json()["items"]] == [
        "customer",
        "staff",
    ]


async def test_technician_with_visible_assignment_can_read_and_reply(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint = await seed_complaint(
        migrated_db_session,
        customer,
        equipment=equipment,
    )
    conversation = await seed_conversation(migrated_db_session, complaint)
    _, technician, technician_token = await seed_technician(
        migrated_db_session
    )
    await _seed_visibility_assignment(
        migrated_db_session,
        complaint,
        technician,
    )

    listing = await api_client.get(
        "/api/v1/conversations",
        headers=bearer(technician_token),
    )
    messages = await api_client.get(
        f"/api/v1/conversations/{conversation.id}/messages",
        headers=bearer(technician_token),
    )
    reply = await api_client.post(
        f"/api/v1/conversations/{conversation.id}/messages",
        headers=_message_headers(
            technician_token,
            _idempotency_key(),
        ),
        json={"content": "Technician response."},
    )

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert messages.status_code == 200
    assert reply.status_code == 201
    assert reply.json()["sender_type"] == "staff"


@pytest.mark.parametrize(
    "assignment_status",
    [
        AssignmentStatus.WITHDRAWN,
        AssignmentStatus.REJECTED,
        AssignmentStatus.EXPIRED,
    ],
)
async def test_technician_without_visible_assignment_cannot_access_conversation(
    api_client: Any,
    migrated_db_session: AsyncSession,
    assignment_status: AssignmentStatus,
) -> None:
    _, customer, _ = await seed_customer(migrated_db_session)
    equipment = await seed_equipment(migrated_db_session, customer)
    complaint = await seed_complaint(
        migrated_db_session,
        customer,
        equipment=equipment,
    )
    conversation = await seed_conversation(migrated_db_session, complaint)
    _, technician, technician_token = await seed_technician(
        migrated_db_session
    )
    await _seed_visibility_assignment(
        migrated_db_session,
        complaint,
        technician,
        assignment_status=assignment_status,
    )

    listing = await api_client.get(
        "/api/v1/conversations",
        headers=bearer(technician_token),
    )
    messages = await api_client.get(
        f"/api/v1/conversations/{conversation.id}/messages",
        headers=bearer(technician_token),
    )
    reply = await api_client.post(
        f"/api/v1/conversations/{conversation.id}/messages",
        headers=_message_headers(
            technician_token,
            _idempotency_key(),
        ),
        json={"content": "Unauthorized reply."},
    )

    assert listing.status_code == 200
    assert listing.json()["total"] == 0
    assert messages.status_code == 404
    assert reply.status_code == 404


async def test_client_cannot_forge_sender_type_or_provider_fields(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, conversation, customer_token = await _seed_owned_conversation(
        migrated_db_session
    )
    _, admin_token = await seed_admin(migrated_db_session)
    url = f"/api/v1/customers/me/conversations/{conversation.id}/messages"

    for payload in (
        {"content": "Forged sender.", "sender_type": "staff"},
        {"content": "Forged assistant.", "sender_type": "assistant"},
        {
            "content": "Forged provider id.",
            "external_message_id": "wa-forged",
        },
    ):
        response = await api_client.post(
            url,
            headers=_message_headers(customer_token, _idempotency_key()),
            json=payload,
        )
        assert response.status_code == 422, payload

    staff_url = f"/api/v1/conversations/{conversation.id}/messages"
    staff_forgery = await api_client.post(
        staff_url,
        headers=_message_headers(admin_token, _idempotency_key()),
        json={"content": "Forged assistant.", "sender_type": "assistant"},
    )
    assert staff_forgery.status_code == 422


async def test_customer_message_creation_persists_trimmed_content(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, conversation, token = await _seed_owned_conversation(
        migrated_db_session
    )

    response = await api_client.post(
        f"/api/v1/customers/me/conversations/{conversation.id}/messages",
        headers=_message_headers(token, _idempotency_key()),
        json={"content": "  The inverter is beeping.  "},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["conversation_id"] == str(conversation.id)
    assert body["sender_type"] == "customer"
    assert body["content"] == "The inverter is beeping."
    assert body["created_at"] is not None

    stored = await migrated_db_session.get(Message, uuid.UUID(body["id"]))
    assert stored is not None
    assert stored.content == "The inverter is beeping."
    assert stored.sender_type is MessageSenderType.CUSTOMER
    assert stored.client_message_id is not None


async def test_blank_and_whitespace_messages_are_rejected(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, conversation, token = await _seed_owned_conversation(
        migrated_db_session
    )
    url = f"/api/v1/customers/me/conversations/{conversation.id}/messages"

    for content in ("", "   ", "\n\t "):
        response = await api_client.post(
            url,
            headers=_message_headers(token, _idempotency_key()),
            json={"content": content},
        )
        assert response.status_code == 422, repr(content)

    assert await _message_count(migrated_db_session) == 0


async def test_maximum_message_length_is_enforced(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, conversation, token = await _seed_owned_conversation(
        migrated_db_session
    )
    url = f"/api/v1/customers/me/conversations/{conversation.id}/messages"

    accepted = await api_client.post(
        url,
        headers=_message_headers(token, _idempotency_key()),
        json={"content": "a" * 10000},
    )
    rejected = await api_client.post(
        url,
        headers=_message_headers(token, _idempotency_key()),
        json={"content": "a" * 10001},
    )

    assert accepted.status_code == 201
    assert len(accepted.json()["content"]) == 10000
    assert rejected.status_code == 422


async def test_messages_are_returned_in_chronological_order(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, conversation, token = await _seed_owned_conversation(
        migrated_db_session
    )
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    await seed_message(
        migrated_db_session,
        conversation,
        content="Third",
        created_at=base + timedelta(minutes=2),
    )
    await seed_message(
        migrated_db_session,
        conversation,
        content="First",
        created_at=base,
    )
    await seed_message(
        migrated_db_session,
        conversation,
        content="Second",
        created_at=base + timedelta(minutes=1),
    )

    response = await api_client.get(
        f"/api/v1/customers/me/conversations/{conversation.id}/messages",
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert [item["content"] for item in response.json()["items"]] == [
        "First",
        "Second",
        "Third",
    ]


async def test_message_pagination_boundaries(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, conversation, token = await _seed_owned_conversation(
        migrated_db_session
    )
    for index in range(3):
        await seed_message(
            migrated_db_session,
            conversation,
            content=f"Message {index}",
        )

    first_page = await api_client.get(
        f"/api/v1/customers/me/conversations/{conversation.id}/messages",
        headers=bearer(token),
        params={"limit": 2, "offset": 0},
    )
    beyond = await api_client.get(
        f"/api/v1/customers/me/conversations/{conversation.id}/messages",
        headers=bearer(token),
        params={"limit": 2, "offset": 4},
    )

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert len(first_page.json()["items"]) == 2
    assert beyond.status_code == 200
    assert beyond.json()["total"] == 3
    assert beyond.json()["items"] == []


async def test_retrying_with_the_same_idempotency_key_returns_same_message(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, conversation, token = await _seed_owned_conversation(
        migrated_db_session
    )
    key = _idempotency_key()
    url = f"/api/v1/customers/me/conversations/{conversation.id}/messages"

    first = await api_client.post(
        url,
        headers=_message_headers(token, key),
        json={"content": "Only once."},
    )
    second = await api_client.post(
        url,
        headers=_message_headers(token, key),
        json={"content": "Only once."},
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    assert await _message_count(migrated_db_session) == 1


async def test_same_idempotency_key_with_different_content_conflicts(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, conversation, token = await _seed_owned_conversation(
        migrated_db_session
    )
    key = _idempotency_key()
    url = f"/api/v1/customers/me/conversations/{conversation.id}/messages"

    first = await api_client.post(
        url,
        headers=_message_headers(token, key),
        json={"content": "Original."},
    )
    conflict = await api_client.post(
        url,
        headers=_message_headers(token, key),
        json={"content": "Changed."},
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert await _message_count(migrated_db_session) == 1


async def test_same_idempotency_key_with_different_sender_conflicts(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, conversation, customer_token = await _seed_owned_conversation(
        migrated_db_session
    )
    _, admin_token = await seed_admin(migrated_db_session)
    key = _idempotency_key()

    customer_message = await api_client.post(
        f"/api/v1/customers/me/conversations/{conversation.id}/messages",
        headers=_message_headers(customer_token, key),
        json={"content": "Same content."},
    )
    staff_message = await api_client.post(
        f"/api/v1/conversations/{conversation.id}/messages",
        headers=_message_headers(admin_token, key),
        json={"content": "Same content."},
    )

    assert customer_message.status_code == 201
    assert staff_message.status_code == 409
    assert (
        staff_message.json()["error"]["code"] == "idempotency_conflict"
    )
    assert await _message_count(migrated_db_session) == 1


def _install_precheck_barrier(monkeypatch: pytest.MonkeyPatch) -> None:
    original = conversation_service.get_message_by_client_message_id
    arrived = 0
    release = asyncio.Event()

    async def gated(
        session: AsyncSession,
        *,
        conversation_id: uuid.UUID,
        client_message_id: str,
    ) -> Message | None:
        nonlocal arrived
        arrived += 1
        if arrived <= 2:
            # Hold both requests before their insert so both observe the key
            # as unused and the database must arbitrate the duplicate.
            if arrived == 2:
                release.set()
            await release.wait()
            return None
        return await original(
            session,
            conversation_id=conversation_id,
            client_message_id=client_message_id,
        )

    monkeypatch.setattr(
        conversation_service,
        "get_message_by_client_message_id",
        gated,
    )


async def test_concurrent_same_key_different_content_returns_conflict(
    api_client: Any,
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, conversation, token = await _seed_owned_conversation(
        migrated_db_session
    )
    key = _idempotency_key()
    _install_precheck_barrier(monkeypatch)
    url = f"/api/v1/customers/me/conversations/{conversation.id}/messages"

    first, second = await asyncio.gather(
        api_client.post(
            url,
            headers=_message_headers(token, key),
            json={"content": "First content."},
        ),
        api_client.post(
            url,
            headers=_message_headers(token, key),
            json={"content": "Second content."},
        ),
    )

    assert sorted([first.status_code, second.status_code]) == [201, 409]
    conflict = first if first.status_code == 409 else second
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert await _message_count(migrated_db_session) == 1


async def test_staff_concurrent_same_key_different_content_returns_conflict(
    api_client: Any,
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, conversation, _ = await _seed_owned_conversation(
        migrated_db_session
    )
    _, admin_token = await seed_admin(migrated_db_session)
    key = _idempotency_key()
    _install_precheck_barrier(monkeypatch)
    url = f"/api/v1/conversations/{conversation.id}/messages"

    first, second = await asyncio.gather(
        api_client.post(
            url,
            headers=_message_headers(admin_token, key),
            json={"content": "First staff content."},
        ),
        api_client.post(
            url,
            headers=_message_headers(admin_token, key),
            json={"content": "Second staff content."},
        ),
    )

    assert sorted([first.status_code, second.status_code]) == [201, 409]
    conflict = first if first.status_code == 409 else second
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert await _message_count(migrated_db_session) == 1


async def test_idempotency_key_is_required(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, conversation, token = await _seed_owned_conversation(
        migrated_db_session
    )

    response = await api_client.post(
        f"/api/v1/customers/me/conversations/{conversation.id}/messages",
        headers=bearer(token),
        json={"content": "No key."},
    )

    assert response.status_code == 422
    assert await _message_count(migrated_db_session) == 0


async def test_concurrent_identical_submissions_create_one_message(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, conversation, token = await _seed_owned_conversation(
        migrated_db_session
    )
    key = _idempotency_key()
    url = f"/api/v1/customers/me/conversations/{conversation.id}/messages"
    headers = _message_headers(token, key)
    payload = {"content": "Concurrent retry."}

    first, second = await asyncio.gather(
        api_client.post(url, headers=headers, json=payload),
        api_client.post(url, headers=headers, json=payload),
    )

    assert sorted([first.status_code, second.status_code]) == [200, 201]
    assert first.json()["id"] == second.json()["id"]
    assert await _message_count(migrated_db_session) == 1


async def test_concurrent_distinct_submissions_create_distinct_messages(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, conversation, token = await _seed_owned_conversation(
        migrated_db_session
    )
    url = f"/api/v1/customers/me/conversations/{conversation.id}/messages"

    first, second = await asyncio.gather(
        api_client.post(
            url,
            headers=_message_headers(token, _idempotency_key()),
            json={"content": "First concurrent message."},
        ),
        api_client.post(
            url,
            headers=_message_headers(token, _idempotency_key()),
            json={"content": "Second concurrent message."},
        ),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert await _message_count(migrated_db_session) == 2


async def test_complaint_creation_creates_a_web_conversation_only(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.post(
        "/api/v1/customers/me/complaints",
        headers=bearer(token),
        json={
            "description": "The inverter stopped generating power.",
            "channel": "whatsapp",
        },
    )

    assert response.status_code == 201
    complaint_id = uuid.UUID(response.json()["id"])
    conversations = (
        await migrated_db_session.execute(
            select(Conversation).where(
                Conversation.complaint_id == complaint_id
            )
        )
    ).scalars().all()
    assert len(conversations) == 1
    assert conversations[0].channel.value == "web"


async def test_complaint_and_message_creation_do_not_trigger_ai_work(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)

    created = await api_client.post(
        "/api/v1/customers/me/complaints",
        headers=bearer(token),
        json={"description": "The inverter stopped generating power."},
    )
    assert created.status_code == 201
    complaint_id = uuid.UUID(created.json()["id"])

    listing = await api_client.get(
        f"/api/v1/customers/me/complaints/{complaint_id}/conversations",
        headers=bearer(token),
    )
    conversation_id = listing.json()["items"][0]["id"]
    message = await api_client.post(
        f"/api/v1/customers/me/conversations/{conversation_id}/messages",
        headers=_message_headers(token, _idempotency_key()),
        json={"content": "Any update?"},
    )
    assert message.status_code == 201

    assert (
        await migrated_db_session.scalar(
            select(func.count(WorkflowRun.id))
        )
        == 0
    )
    assert (
        await migrated_db_session.scalar(
            select(func.count(BackgroundTask.id))
        )
        == 0
    )
    assert (
        await migrated_db_session.scalar(
            select(func.count(OutboxEvent.id))
        )
        == 0
    )


async def test_cancelled_complaint_keeps_conversation_readable(
    api_client: Any,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)
    complaint = await seed_complaint(migrated_db_session, customer)
    conversation = await seed_conversation(migrated_db_session, complaint)
    await seed_message(migrated_db_session, conversation)

    cancelled = await api_client.post(
        f"/api/v1/customers/me/complaints/{complaint.id}/cancel",
        headers=bearer(token),
    )
    listing = await api_client.get(
        f"/api/v1/customers/me/complaints/{complaint.id}/conversations",
        headers=bearer(token),
    )
    history = await api_client.get(
        f"/api/v1/customers/me/conversations/{conversation.id}/messages",
        headers=bearer(token),
    )

    assert cancelled.status_code == 200
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert history.status_code == 200
    assert history.json()["total"] == 1


async def test_openapi_exposes_conversation_and_message_contracts(
    api_client: Any,
) -> None:
    response = await api_client.get("/openapi.json")

    assert response.status_code == 200
    document = response.json()
    paths = document["paths"]
    assert (
        "/api/v1/customers/me/complaints/{complaint_id}/conversations"
        in paths
    )
    assert (
        "/api/v1/customers/me/conversations/{conversation_id}/messages"
        in paths
    )
    assert "/api/v1/conversations" in paths
    assert "/api/v1/conversations/{conversation_id}/messages" in paths

    customer_post = paths[
        "/api/v1/customers/me/conversations/{conversation_id}/messages"
    ]["post"]
    parameters = {
        parameter["name"]: parameter
        for parameter in customer_post.get("parameters", [])
    }
    assert parameters["Idempotency-Key"]["in"] == "header"
    assert parameters["Idempotency-Key"]["required"] is True
    assert "201" in customer_post["responses"]

    schemas = document["components"]["schemas"]
    message_create = schemas["MessageCreate"]
    assert set(message_create["properties"]) == {"content"}
    assert message_create.get("additionalProperties") is False
