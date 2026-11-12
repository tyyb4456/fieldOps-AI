from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from tests.support import (
    bearer,
    seed_admin,
    seed_customer,
    seed_technician,
)


async def test_customer_profile_requires_authentication(api_client) -> None:
    response = await api_client.get("/api/v1/customers/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_customer_can_read_own_profile(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _user, customer, token = await seed_customer(
        migrated_db_session,
        full_name="Ahmed Khan",
        address="45 Solar Avenue",
        preferred_language="ur",
    )

    response = await api_client.get(
        "/api/v1/customers/me",
        headers=bearer(token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(customer.id)
    assert payload["full_name"] == "Ahmed Khan"
    assert payload["address"] == "45 Solar Avenue"
    assert payload["preferred_language"] == "ur"
    assert payload["is_active"] is True
    assert "user_id" not in payload
    assert "clerk_user_id" not in payload
    assert "role" not in payload


async def test_customer_can_update_permitted_fields(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, token = await seed_customer(migrated_db_session)

    response = await api_client.patch(
        "/api/v1/customers/me",
        headers=bearer(token),
        json={
            "address": "  99 New Street  ",
            "preferred_language": "en",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["address"] == "99 New Street"
    assert payload["preferred_language"] == "en"

    await migrated_db_session.refresh(customer)
    assert customer.address == "99 New Street"


async def test_customer_cannot_change_identity_or_authorization_fields(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)

    forbidden_payloads = [
        {"role": "admin"},
        {"clerk_user_id": "user_attacker"},
        {"is_active": False},
        {"user_id": str(uuid.uuid4())},
        {"full_name": "Changed Name"},
        {"technician_id": str(uuid.uuid4())},
    ]

    for payload in forbidden_payloads:
        response = await api_client.patch(
            "/api/v1/customers/me",
            headers=bearer(token),
            json=payload,
        )
        assert response.status_code == 422, payload
        assert response.json()["error"]["code"] == "validation_error"


async def test_customer_profile_update_requires_a_field(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.patch(
        "/api/v1/customers/me",
        headers=bearer(token),
        json={},
    )

    assert response.status_code == 422


async def test_customer_profile_update_validates_lengths(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.patch(
        "/api/v1/customers/me",
        headers=bearer(token),
        json={"preferred_language": "x" * 31},
    )

    assert response.status_code == 422


async def test_customer_cannot_read_another_customer_profile(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, other, _ = await seed_customer(migrated_db_session)
    _, _, token = await seed_customer(migrated_db_session)

    response = await api_client.get(
        f"/api/v1/customers/{other.id}",
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_technician_cannot_use_customer_profile_endpoints(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_technician(migrated_db_session)

    read_response = await api_client.get(
        "/api/v1/customers/me",
        headers=bearer(token),
    )
    update_response = await api_client.patch(
        "/api/v1/customers/me",
        headers=bearer(token),
        json={"address": "Nope"},
    )

    assert read_response.status_code == 403
    assert update_response.status_code == 403


async def test_admin_can_read_any_customer_profile(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(
        migrated_db_session,
        full_name="Bilal",
    )
    _, admin_token = await seed_admin(migrated_db_session)

    response = await api_client.get(
        f"/api/v1/customers/{customer.id}",
        headers=bearer(admin_token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(customer.id)
    assert payload["full_name"] == "Bilal"


async def test_admin_profile_endpoint_returns_not_found_for_unknown_id(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)

    response = await api_client.get(
        f"/api/v1/customers/{uuid.uuid4()}",
        headers=bearer(admin_token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_admin_cannot_use_customer_only_profile_endpoint(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, admin_token = await seed_admin(migrated_db_session)

    response = await api_client.get(
        "/api/v1/customers/me",
        headers=bearer(admin_token),
    )

    assert response.status_code == 403
