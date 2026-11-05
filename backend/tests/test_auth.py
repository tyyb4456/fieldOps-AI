from __future__ import annotations

import time
import uuid

import jwt
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.dependencies.auth import require_roles
from app.core.exceptions import AppError
from app.models.customer import Customer
from app.models.equipment import Equipment
from app.models.enums import UserRole
from app.models.technician import Technician
from app.models.user import User
from app.services.accounts import (
    AccountConflictError,
    ProfileInvariantError,
    ensure_profile_invariant,
    get_or_provision_user,
    provision_user,
    set_user_role,
)
from app.services.clerk_auth import (
    ClerkAuthenticationError,
    ClerkConfigurationError,
    ClerkIdentity,
    ClerkProfile,
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


def make_identity(
    *,
    clerk_user_id: str | None = None,
    email: str | None = None,
    email_verified: bool = False,
    phone: str | None = None,
    phone_verified: bool = False,
    full_name: str | None = None,
    claims: dict[str, object] | None = None,
) -> ClerkIdentity:
    return ClerkIdentity(
        clerk_user_id=clerk_user_id or f"user_{uuid.uuid4().hex}",
        session_id="sess_test",
        claims=claims or {},
        profile=ClerkProfile(
            email=email,
            email_verified=email_verified,
            phone=phone,
            phone_verified=phone_verified,
            full_name=full_name,
        ),
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


def test_verify_clerk_token_accepts_session_cookie() -> None:
    token = make_clerk_token(sub="user_cookie")

    identity = verify_clerk_token(
        make_request(cookie_token=token),
        secret_key=None,
        jwt_key=TEST_CLERK_PUBLIC_KEY,
        authorized_parties=[TEST_CLERK_AUTHORIZED_PARTY],
    )

    assert identity.clerk_user_id == "user_cookie"


def test_verify_clerk_token_rejects_missing_token() -> None:
    with pytest.raises(ClerkAuthenticationError) as exc_info:
        verify_clerk_token(
            make_request(),
            secret_key=None,
            jwt_key=TEST_CLERK_PUBLIC_KEY,
            authorized_parties=[TEST_CLERK_AUTHORIZED_PARTY],
        )

    assert exc_info.value.reason == "session-token-missing"


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


def test_verify_clerk_token_requires_configuration() -> None:
    token = make_clerk_token()

    with pytest.raises(ClerkConfigurationError):
        verify_clerk_token(
            make_request(token=token),
            secret_key=None,
            jwt_key=None,
            authorized_parties=[TEST_CLERK_AUTHORIZED_PARTY],
        )


async def test_provision_creates_customer_profile(
    db_session: AsyncSession,
) -> None:
    identity = make_identity(
        email="new@example.com",
        email_verified=True,
        full_name="New Customer",
    )

    user = await provision_user(db_session, identity)
    await db_session.flush()

    assert user.id is not None
    assert user.role is UserRole.CUSTOMER
    assert user.customer is not None
    assert user.technician is None
    assert user.email == "new@example.com"
    assert user.password_hash is None
    assert user.clerk_user_id == identity.clerk_user_id


async def test_provision_is_idempotent(db_session: AsyncSession) -> None:
    identity = make_identity(full_name="Repeat User")

    first = await provision_user(db_session, identity)
    await db_session.flush()
    second = await provision_user(db_session, identity)

    assert second.id == first.id
    count = await db_session.scalar(
        select(func.count(User.id)).where(
            User.clerk_user_id == identity.clerk_user_id
        )
    )
    assert count == 1


async def test_provision_links_existing_user_by_verified_email(
    db_session: AsyncSession,
) -> None:
    email = f"{uuid.uuid4().hex}@example.com"
    existing = User(
        full_name="Existing Customer",
        email=email,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    existing.customer = Customer()
    db_session.add(existing)
    await db_session.flush()

    identity = make_identity(
        email=email,
        email_verified=True,
    )
    user = await provision_user(db_session, identity)

    assert user.id == existing.id
    assert user.clerk_user_id == identity.clerk_user_id


async def test_provision_does_not_link_unverified_email(
    db_session: AsyncSession,
) -> None:
    email = f"{uuid.uuid4().hex}@example.com"
    existing = User(
        full_name="Existing Customer",
        email=email,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    existing.customer = Customer()
    db_session.add(existing)
    await db_session.flush()

    identity = make_identity(
        email=email,
        email_verified=False,
    )
    user = await provision_user(db_session, identity)
    await db_session.flush()

    assert user.id != existing.id
    assert user.email is None
    assert existing.clerk_user_id is None


async def test_provision_rejects_verified_email_conflict(
    db_session: AsyncSession,
) -> None:
    email = f"{uuid.uuid4().hex}@example.com"
    existing = User(
        full_name="Existing Customer",
        email=email,
        clerk_user_id=f"user_{uuid.uuid4().hex}",
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    existing.customer = Customer()
    db_session.add(existing)
    await db_session.flush()

    with pytest.raises(AccountConflictError):
        await provision_user(
            db_session,
            make_identity(email=email, email_verified=True),
        )


async def test_provision_rejects_verified_phone_conflict(
    db_session: AsyncSession,
) -> None:
    phone = f"+1555{uuid.uuid4().int % 10_000_000:07d}"
    existing = User(
        full_name="Existing Customer",
        phone=phone,
        clerk_user_id=f"user_{uuid.uuid4().hex}",
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    existing.customer = Customer()
    db_session.add(existing)
    await db_session.flush()

    with pytest.raises(AccountConflictError):
        await provision_user(
            db_session,
            make_identity(phone=phone, phone_verified=True),
        )


async def test_provision_ignores_role_claims(db_session: AsyncSession) -> None:
    identity = make_identity(
        claims={
            "role": "admin",
            "unsafe_metadata": {"role": "admin"},
            "public_metadata": {"role": "admin"},
        },
    )

    user = await provision_user(db_session, identity)

    assert user.role is UserRole.CUSTOMER


async def test_provision_preserves_existing_database_role(
    db_session: AsyncSession,
) -> None:
    clerk_user_id = f"user_{uuid.uuid4().hex}"
    existing = User(
        full_name="Existing Technician",
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.TECHNICIAN,
    )
    existing.technician = Technician()
    db_session.add(existing)
    await db_session.flush()

    user = await provision_user(
        db_session,
        make_identity(clerk_user_id=clerk_user_id),
    )

    assert user.id == existing.id
    assert user.role is UserRole.TECHNICIAN
    assert user.technician is not None
    assert user.customer is None


async def test_provision_rejects_customer_with_technician_profile(
    db_session: AsyncSession,
) -> None:
    clerk_user_id = f"user_{uuid.uuid4().hex}"
    existing = User(
        full_name="Broken Customer",
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    existing.technician = Technician()
    db_session.add(existing)
    await db_session.flush()

    with pytest.raises(ProfileInvariantError):
        await provision_user(
            db_session,
            make_identity(clerk_user_id=clerk_user_id),
        )


async def test_provision_rejects_admin_with_operational_profile(
    db_session: AsyncSession,
) -> None:
    clerk_user_id = f"user_{uuid.uuid4().hex}"
    existing = User(
        full_name="Broken Admin",
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.ADMIN,
    )
    existing.customer = Customer()
    db_session.add(existing)
    await db_session.flush()

    with pytest.raises(ProfileInvariantError):
        await provision_user(
            db_session,
            make_identity(clerk_user_id=clerk_user_id),
        )


async def test_ensure_profile_invariant_creates_missing_profiles(
    db_session: AsyncSession,
) -> None:
    customer_user = User(
        full_name="Customer",
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    technician_user = User(
        full_name="Technician",
        password_hash=None,
        role=UserRole.TECHNICIAN,
    )
    admin_user = User(
        full_name="Admin",
        password_hash=None,
        role=UserRole.ADMIN,
    )
    db_session.add_all([customer_user, technician_user, admin_user])
    await db_session.flush()

    await ensure_profile_invariant(db_session, customer_user)
    await ensure_profile_invariant(db_session, technician_user)
    await ensure_profile_invariant(db_session, admin_user)

    assert customer_user.customer is not None
    assert customer_user.technician is None
    assert technician_user.technician is not None
    assert technician_user.customer is None
    assert admin_user.customer is None
    assert admin_user.technician is None


async def test_set_user_role_promotes_empty_customer_to_technician(
    db_session: AsyncSession,
) -> None:
    user = User(
        full_name="Promote Me",
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    user.customer = Customer()
    db_session.add(user)
    await db_session.flush()

    await set_user_role(db_session, user, UserRole.TECHNICIAN)

    assert user.role is UserRole.TECHNICIAN
    assert user.customer is None
    assert user.technician is not None


async def test_set_user_role_promotes_customer_to_admin(
    db_session: AsyncSession,
) -> None:
    user = User(
        full_name="Promote Admin",
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    user.customer = Customer()
    db_session.add(user)
    await db_session.flush()

    await set_user_role(db_session, user, UserRole.ADMIN)

    assert user.role is UserRole.ADMIN
    assert user.customer is None
    assert user.technician is None


async def test_set_user_role_refuses_to_remove_operational_profile(
    db_session: AsyncSession,
) -> None:
    user = User(
        full_name="Has Equipment",
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    user.customer = Customer()
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        Equipment(
            customer=user.customer,
            manufacturer="Acme",
            model="INV-5000",
            equipment_type="solar_inverter",
        )
    )
    await db_session.flush()

    with pytest.raises(ProfileInvariantError):
        await set_user_role(db_session, user, UserRole.ADMIN)

    assert user.role is UserRole.CUSTOMER
    assert user.customer is not None


async def test_get_or_provision_user_recovers_from_integrity_error(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clerk_user_id = f"user_{uuid.uuid4().hex}"
    existing = User(
        full_name="Existing",
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    existing.customer = Customer()
    migrated_db_session.add(existing)
    await migrated_db_session.commit()
    existing_id = existing.id

    async def raise_integrity_error(*args: object, **kwargs: object) -> None:
        raise IntegrityError("statement", {}, Exception("duplicate"))

    monkeypatch.setattr(
        "app.services.accounts._provision",
        raise_integrity_error,
    )

    user = await get_or_provision_user(
        migrated_db_session,
        make_identity(clerk_user_id=clerk_user_id),
    )

    assert user.id == existing_id


async def test_get_or_provision_user_raises_conflict_when_unrecoverable(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def raise_integrity_error(*args: object, **kwargs: object) -> None:
        raise IntegrityError("statement", {}, Exception("duplicate"))

    monkeypatch.setattr(
        "app.services.accounts._provision",
        raise_integrity_error,
    )

    with pytest.raises(AccountConflictError):
        await get_or_provision_user(
            migrated_db_session,
            make_identity(),
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


async def test_users_me_requires_authentication(
    api_client,
) -> None:
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


async def test_users_me_provisions_customer(api_client) -> None:
    token = make_clerk_token(
        email="api-new@example.com",
        email_verified=True,
        name="API User",
    )

    response = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "customer"
    assert payload["email"] == "api-new@example.com"
    assert payload["customer_id"] is not None
    assert payload["technician_id"] is None
    assert payload["is_active"] is True


async def test_users_me_is_idempotent(api_client) -> None:
    subject = f"user_{uuid.uuid4().hex}"
    token = make_clerk_token(sub=subject)

    first = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )
    second = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


async def test_users_me_ignores_role_claims(api_client) -> None:
    token = make_clerk_token(
        role="admin",
        unsafe_metadata={"role": "admin"},
        public_metadata={"role": "admin"},
    )

    response = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "customer"


async def test_users_me_rejects_inactive_user(
    api_client,
    migrated_db_session: AsyncSession,
) -> None:
    subject = f"user_{uuid.uuid4().hex}"
    token = make_clerk_token(sub=subject)

    created = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )
    user_id = uuid.UUID(created.json()["id"])

    user = await migrated_db_session.get(User, user_id)
    assert user is not None
    user.is_active = False
    await migrated_db_session.commit()

    response = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_inactive"


async def test_users_me_returns_conflict_for_verified_email(
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
    response = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_conflict"


async def test_users_me_links_existing_user_by_verified_email(
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
    response = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(existing_id)

    refreshed = await migrated_db_session.get(User, existing_id)
    assert refreshed is not None
    await migrated_db_session.refresh(refreshed)
    assert refreshed.clerk_user_id == subject


async def test_users_me_does_not_link_unverified_email(
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
    response = await api_client.get(
        "/api/v1/users/me",
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()["id"] != str(existing_id)
    assert response.json()["email"] is None

    refreshed = await migrated_db_session.get(User, existing_id)
    assert refreshed is not None
    await migrated_db_session.refresh(refreshed)
    assert refreshed.clerk_user_id is None


async def test_users_me_rejects_invalid_profile_invariant(
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


async def test_health_endpoints_remain_public(api_client) -> None:
    response = await api_client.get("/api/v1/health")

    assert response.status_code == 200
