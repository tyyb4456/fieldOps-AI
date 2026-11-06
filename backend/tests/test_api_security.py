from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_clerk_token
from tests.support import (
    bearer,
    seed_admin,
    seed_customer,
    seed_technician,
)


CUSTOMER_ENDPOINTS = [
    ("get", "/api/v1/customers/me"),
    ("get", "/api/v1/customers/me/equipment"),
    ("get", "/api/v1/customers/me/complaints"),
]

ADMIN_ENDPOINTS = [
    ("get", "/api/v1/admin/equipment"),
    ("get", "/api/v1/admin/complaints"),
    (
        "get",
        f"/api/v1/admin/complaints/{uuid.uuid4()}/history",
    ),
    ("get", f"/api/v1/customers/{uuid.uuid4()}"),
]


@pytest.mark.parametrize("method,path", CUSTOMER_ENDPOINTS + ADMIN_ENDPOINTS)
async def test_missing_credentials_are_rejected(
    api_client,
    method: str,
    path: str,
) -> None:
    response = await getattr(api_client, method)(path)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("method,path", CUSTOMER_ENDPOINTS + ADMIN_ENDPOINTS)
async def test_malformed_bearer_token_is_rejected(
    api_client,
    method: str,
    path: str,
) -> None:
    response = await getattr(api_client, method)(
        path,
        headers={"Authorization": "Bearer not-a-jwt"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_expired_token_is_rejected(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    user, _, _ = await seed_customer(migrated_db_session)
    now = int(time.time())
    expired = make_clerk_token(
        sub=user.clerk_user_id,
        iat=now - 600,
        nbf=now - 600,
        exp=now - 300,
    )

    response = await api_client.get(
        "/api/v1/customers/me",
        headers=bearer(expired),
    )

    assert response.status_code == 401


async def test_token_for_unknown_identity_has_no_account_access(
    api_client,
) -> None:
    response = await api_client.get(
        "/api/v1/customers/me",
        headers=bearer(make_clerk_token()),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "account_not_provisioned"


async def test_inactive_customer_is_denied(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(
        migrated_db_session,
        is_active=False,
    )

    response = await api_client.get(
        "/api/v1/customers/me",
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_inactive"


async def test_inactive_technician_is_denied(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_technician(
        migrated_db_session,
        is_active=False,
    )

    response = await api_client.get(
        "/api/v1/customers/me/equipment",
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_inactive"


async def test_inactive_admin_is_denied(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, token = await seed_admin(
        migrated_db_session,
        is_active=False,
    )

    response = await api_client.get(
        "/api/v1/admin/equipment",
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_inactive"


async def test_customer_role_cannot_reach_admin_endpoints(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_customer(migrated_db_session)

    for method, path in ADMIN_ENDPOINTS:
        response = await getattr(api_client, method)(
            path,
            headers=bearer(token),
        )
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "forbidden"


async def test_technician_role_cannot_reach_customer_endpoints(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, _, token = await seed_technician(migrated_db_session)

    for method, path in CUSTOMER_ENDPOINTS:
        response = await getattr(api_client, method)(
            path,
            headers=bearer(token),
        )
        assert response.status_code == 403, path


async def test_admin_role_cannot_reach_customer_only_endpoints(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    _, token = await seed_admin(migrated_db_session)

    for method, path in CUSTOMER_ENDPOINTS:
        response = await getattr(api_client, method)(
            path,
            headers=bearer(token),
        )
        assert response.status_code == 403, path
