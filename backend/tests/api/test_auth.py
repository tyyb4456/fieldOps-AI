from __future__ import annotations

import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.dependencies.auth import require_roles
from app.core.config import settings
from app.core.exceptions import AppError
from app.main import app
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.technician import Technician
from app.models.user import User
from app.services.accounts.clerk_auth import (
    ClerkAuthenticationError,
    ClerkConfigurationError,
    identity_from_payload,
    verify_clerk_token,
)
from tests.conftest import (
    TEST_CLERK_AUTHORIZED_PARTY,
    TEST_CLERK_PUBLIC_KEY,
    make_clerk_token,
)


def make_request(
    *,
    token: str | None = None,
    cookie_token: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if token is not None:
        headers.append(
            (b"authorization", f"Bearer {token}".encode())
        )
    if cookie_token is not None:
        headers.append(
            (b"cookie", f"__session={cookie_token}".encode())
        )
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/users/me",
            "headers": headers,
        }
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def bootstrap(api_client, token: str):
    return await api_client.post(
        "/api/v1/auth/bootstrap",
        headers=bearer(token),
    )


def test_identity_from_payload_uses_only_signed_claims() -> None:
    identity = identity_from_payload(
        {
            "sub": "user_123",
            "sid": "sess_123",
            "email": "person@example.com",
            "email_verified": True,
            "first_name": "Ada",
            "last_name": "Lovelace",
        }
    )

    assert identity.clerk_user_id == "user_123"
    assert identity.session_id == "sess_123"
    assert identity.profile.email == "person@example.com"
    assert identity.profile.email_verified is True
    assert identity.profile.full_name == "Ada Lovelace"


def test_identity_from_payload_requires_subject() -> None:
    with pytest.raises(ClerkAuthenticationError):
        identity_from_payload({"sid": "sess_123"})


def test_verify_clerk_token_accepts_bearer_token() -> None:
    token = make_clerk_token(sub="user_valid")

    identity = verify_clerk_token(
        make_request(token=token),
        secret_key=None,
        jwt_key=TEST_CLERK_PUBLIC_KEY,
        authorized_parties=[TEST_CLERK_AUTHORIZED_PARTY],
    )

    assert identity.clerk_user_id == "user_valid"


def test_verify_clerk_token_rejects_cookie_only() -> None:
    token = make_clerk_token(sub="user_cookie")

    with pytest.raises(ClerkAuthenticationError) as exc_info:
        verify_clerk_token(
            make_request(cookie_token=token),
            secret_key=None,
            jwt_key=TEST_CLERK_PUBLIC_KEY,
            authorized_parties=[TEST_CLERK_AUTHORIZED_PARTY],
        )

    assert exc_info.value.reason == "bearer-token-missing"


def test_verify_clerk_token_rejects_missing_token() -> None:
    with pytest.raises(ClerkAuthenticationError) as exc_info:
        verify_clerk_token(
            make_request(),
            secret_key=None,
            jwt_key=TEST_CLERK_PUBLIC_KEY,
            authorized_parties=[TEST_CLERK_AUTHORIZED_PARTY],
        )

    assert exc_info.value.reason == "bearer-token-missing"


def test_verify_clerk_token_rejects_unsupported_scheme() -> None:
    token = make_clerk_token()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/users/me",
            "headers": [(b"authorization", f"Basic {token}".encode())],
        }
    )

    with pytest.raises(ClerkAuthenticationError) as exc_info:
        verify_clerk_token(
            request,
            secret_key=None,
            jwt_key=TEST_CLERK_PUBLIC_KEY,
            authorized_parties=[TEST_CLERK_AUTHORIZED_PARTY],
        )

    assert exc_info.value.reason == "unsupported-authorization-scheme"


def test_verify_clerk_token_rejects_invalid_signature() -> None:
    token = jwt.encode(
        {
            "sub": "user_forged",
            "azp": TEST_CLERK_AUTHORIZED_PARTY,
            "exp": int(time.time()) + 300,
        },
        "not-the-clerk-signing-key-but-at-least-32-bytes",
        algorithm="HS256",
    )

    with pytest.raises(ClerkAuthenticationError):
        verify_clerk_token(
            make_request(token=token),
            secret_key=None,
            jwt_key=TEST_CLERK_PUBLIC_KEY,
            authorized_parties=[TEST_CLERK_AUTHORIZED_PARTY],
        )


def test_verify_clerk_token_rejects_untrusted_authorized_party() -> None:
    token = make_clerk_token(azp="https://evil.example.com")

    with pytest.raises(ClerkAuthenticationError):
        verify_clerk_token(
            make_request(token=token),
            secret_key=None,
            jwt_key=TEST_CLERK_PUBLIC_KEY,
            authorized_parties=[TEST_CLERK_AUTHORIZED_PARTY],
        )


def test_verify_clerk_token_rejects_missing_authorized_party() -> None:
    token = make_clerk_token(azp=None)

    with pytest.raises(ClerkAuthenticationError) as exc_info:
        verify_clerk_token(
            make_request(token=token),
            secret_key=None,
            jwt_key=TEST_CLERK_PUBLIC_KEY,
            authorized_parties=[TEST_CLERK_AUTHORIZED_PARTY],
        )

    assert exc_info.value.reason == "token-invalid-authorized-parties"


def test_verify_clerk_token_empty_parties_rejects_everything() -> None:
    token = make_clerk_token(azp=TEST_CLERK_AUTHORIZED_PARTY)

    with pytest.raises(ClerkAuthenticationError) as exc_info:
        verify_clerk_token(
            make_request(token=token),
            secret_key=None,
            jwt_key=TEST_CLERK_PUBLIC_KEY,
            authorized_parties=[],
        )

    assert exc_info.value.reason == "token-invalid-authorized-parties"


def test_verify_clerk_token_rejects_expired_token() -> None:
    now = int(time.time())
    token = make_clerk_token(
        iat=now - 600,
        nbf=now - 600,
        exp=now - 300,
    )

    with pytest.raises(ClerkAuthenticationError):
        verify_clerk_token(
            make_request(token=token),
            secret_key=None,
            jwt_key=TEST_CLERK_PUBLIC_KEY,
            authorized_parties=[TEST_CLERK_AUTHORIZED_PARTY],
        )


def test_verify_clerk_token_requires_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "clerk_secret_key", None)
    monkeypatch.setattr(settings, "clerk_jwt_key", None)
    token = make_clerk_token()

    with pytest.raises(ClerkConfigurationError):
        verify_clerk_token(
            make_request(token=token),
            secret_key=None,
            jwt_key=None,
            authorized_parties=[TEST_CLERK_AUTHORIZED_PARTY],
        )


async def test_require_roles_allows_matching_role() -> None:
    user = User(
        full_name="Admin",
        password_hash=None,
        role=UserRole.ADMIN,
    )
    dependency = require_roles(UserRole.ADMIN)

    result = await dependency(current_user=user)

    assert result is user


async def test_require_roles_rejects_wrong_role() -> None:
    user = User(
        full_name="Customer",
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    dependency = require_roles(UserRole.ADMIN)

    with pytest.raises(AppError) as exc_info:
        await dependency(current_user=user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "forbidden"


async def test_users_me_requires_authentication(api_client) -> None:
    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert response.headers["www-authenticate"] == "Bearer"


async def test_users_me_rejects_invalid_token(api_client) -> None:
    token = jwt.encode(
        {"sub": "user_forged", "exp": int(time.time()) + 300},
        "wrong-key-that-is-at-least-32-bytes-long",
        algorithm="HS256",
    )

    response = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )

    assert response.status_code == 401


async def test_users_me_rejects_cookie_session(api_client) -> None:
    token = make_clerk_token()

    response = await api_client.get(
        "/api/v1/users/me",
        headers={"Cookie": f"__session={token}"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_invalid_bearer_does_not_fall_back_to_cookie(api_client) -> None:
    cookie_token = make_clerk_token()
    forged = jwt.encode(
        {"sub": "user_forged", "exp": int(time.time()) + 300},
        "wrong-key-that-is-at-least-32-bytes-long",
        algorithm="HS256",
    )

    response = await api_client.get(
        "/api/v1/users/me",
        headers={
            "Authorization": f"Bearer {forged}",
            "Cookie": f"__session={cookie_token}",
        },
    )

    assert response.status_code == 401


async def test_users_me_rejects_missing_azp(api_client) -> None:
    token = make_clerk_token(azp=None)

    response = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )

    assert response.status_code == 401


async def test_unexpected_verification_failure_is_401(
    api_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("unexpected clerk failure")

    monkeypatch.setattr(
        "app.api.dependencies.auth.verify_clerk_token",
        boom,
    )

    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert response.headers["www-authenticate"] == "Bearer"


def test_internal_failure_is_not_masked_as_401(
    auth_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        "app.api.dependencies.auth.find_user_by_clerk_id",
        boom,
    )

    token = make_clerk_token()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/users/me",
            headers=bearer(token),
        )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_server_error"


async def test_get_me_does_not_provision(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    subject = f"user_{uuid.uuid4().hex}"
    token = make_clerk_token(sub=subject)

    response = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "account_not_provisioned"
    count = await migrated_db_session.scalar(
        select(func.count(User.id)).where(User.clerk_user_id == subject)
    )
    assert count == 0


async def test_bootstrap_provisions_customer(api_client) -> None:
    token = make_clerk_token(
        email="Api-New@Example.com",
        email_verified=True,
        name="API User",
    )

    response = await bootstrap(api_client, token)

    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "customer"
    assert payload["email"] == "api-new@example.com"
    assert payload["customer_id"] is not None
    assert payload["technician_id"] is None
    assert payload["is_active"] is True


async def test_get_me_is_read_only_after_bootstrap(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    subject = f"user_{uuid.uuid4().hex}"
    token = make_clerk_token(sub=subject)

    created = await bootstrap(api_client, token)
    assert created.status_code == 200

    before = await migrated_db_session.scalar(
        select(func.count(User.id))
    )
    response = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )
    after = await migrated_db_session.scalar(select(func.count(User.id)))

    assert response.status_code == 200
    assert response.json()["id"] == created.json()["id"]
    assert before == after


async def test_bootstrap_is_idempotent(api_client) -> None:
    subject = f"user_{uuid.uuid4().hex}"
    token = make_clerk_token(sub=subject)

    first = await bootstrap(api_client, token)
    second = await bootstrap(api_client, token)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


async def test_bootstrap_ignores_role_claims(api_client) -> None:
    token = make_clerk_token(
        role="admin",
        unsafe_metadata={"role": "admin"},
        public_metadata={"role": "admin"},
    )

    response = await bootstrap(api_client, token)

    assert response.status_code == 200
    assert response.json()["role"] == "customer"


async def test_inactive_user_is_rejected(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    subject = f"user_{uuid.uuid4().hex}"
    token = make_clerk_token(sub=subject)

    created = await bootstrap(api_client, token)
    user_id = uuid.UUID(created.json()["id"])

    user = await migrated_db_session.get(User, user_id)
    assert user is not None
    user.is_active = False
    await migrated_db_session.commit()

    me_response = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )
    bootstrap_response = await bootstrap(api_client, token)

    assert me_response.status_code == 403
    assert me_response.json()["error"]["code"] == "account_inactive"
    assert bootstrap_response.status_code == 403
    assert bootstrap_response.json()["error"]["code"] == "account_inactive"


async def test_bootstrap_returns_conflict_for_verified_email(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    email = f"{uuid.uuid4().hex}@example.com"
    existing = User(
        full_name="Existing",
        email=email,
        clerk_user_id=f"user_{uuid.uuid4().hex}",
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    existing.customer = Customer()
    migrated_db_session.add(existing)
    await migrated_db_session.commit()

    token = make_clerk_token(email=email, email_verified=True)
    response = await bootstrap(api_client, token)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_conflict"


async def test_bootstrap_rejects_privileged_email_linking(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    email = f"{uuid.uuid4().hex}@example.com"
    admin = User(
        full_name="Admin",
        email=email,
        password_hash=None,
        role=UserRole.ADMIN,
    )
    migrated_db_session.add(admin)
    await migrated_db_session.commit()
    admin_id = admin.id

    token = make_clerk_token(email=email, email_verified=True)
    response = await bootstrap(api_client, token)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_conflict"

    refreshed = await migrated_db_session.get(User, admin_id)
    assert refreshed is not None
    await migrated_db_session.refresh(refreshed)
    assert refreshed.clerk_user_id is None


async def test_bootstrap_links_existing_customer_by_verified_email(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    email = f"{uuid.uuid4().hex}@example.com"
    existing = User(
        full_name="Existing",
        email=email,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    existing.customer = Customer()
    migrated_db_session.add(existing)
    await migrated_db_session.commit()
    existing_id = existing.id

    subject = f"user_{uuid.uuid4().hex}"
    token = make_clerk_token(
        sub=subject,
        email=email,
        email_verified=True,
    )
    response = await bootstrap(api_client, token)

    assert response.status_code == 200
    assert response.json()["id"] == str(existing_id)

    refreshed = await migrated_db_session.get(User, existing_id)
    assert refreshed is not None
    await migrated_db_session.refresh(refreshed)
    assert refreshed.clerk_user_id == subject


async def test_bootstrap_does_not_link_unverified_email(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    email = f"{uuid.uuid4().hex}@example.com"
    existing = User(
        full_name="Existing",
        email=email,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    existing.customer = Customer()
    migrated_db_session.add(existing)
    await migrated_db_session.commit()
    existing_id = existing.id

    token = make_clerk_token(email=email, email_verified=False)
    response = await bootstrap(api_client, token)

    assert response.status_code == 200
    assert response.json()["id"] != str(existing_id)
    assert response.json()["email"] is None

    refreshed = await migrated_db_session.get(User, existing_id)
    assert refreshed is not None
    await migrated_db_session.refresh(refreshed)
    assert refreshed.clerk_user_id is None


async def test_get_me_rejects_invalid_profile_invariant(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    subject = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name="Broken",
        clerk_user_id=subject,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    user.technician = Technician()
    migrated_db_session.add(user)
    await migrated_db_session.commit()

    token = make_clerk_token(sub=subject)
    response = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "account_configuration_error"


async def test_bootstrap_ip_rate_limit(
    api_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "auth_bootstrap_rate_limit_per_ip",
        2,
    )
    monkeypatch.setattr(
        settings,
        "auth_bootstrap_rate_limit_per_subject",
        100,
    )

    first = await bootstrap(api_client, make_clerk_token())
    second = await bootstrap(api_client, make_clerk_token())
    third = await bootstrap(api_client, make_clerk_token())

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "rate_limited"
    assert int(third.headers["retry-after"]) >= 1


async def test_bootstrap_subject_rate_limit(
    api_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "auth_bootstrap_rate_limit_per_ip",
        100,
    )
    monkeypatch.setattr(
        settings,
        "auth_bootstrap_rate_limit_per_subject",
        1,
    )

    token = make_clerk_token()
    first = await bootstrap(api_client, token)
    second = await bootstrap(api_client, token)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"


async def test_cors_allows_configured_origin(api_client) -> None:
    response = await api_client.options(
        "/api/v1/users/me",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:5173"
    )


async def test_cors_rejects_unknown_origin(api_client) -> None:
    response = await api_client.options(
        "/api/v1/users/me",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers


async def test_health_endpoints_remain_public(api_client) -> None:
    response = await api_client.get("/api/v1/health")

    assert response.status_code == 200
