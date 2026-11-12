from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.equipment import Equipment
from app.models.technician import Technician
from app.models.user import User
from app.services.accounts import (
    DEFAULT_FULL_NAME,
    MAX_PROFILE_ENRICHMENT_ATTEMPTS,
    AccountConflictError,
    ProfileInvariantError,
    ensure_profile_invariant,
    get_or_provision_user,
    link_clerk_identity,
    provision_user,
    set_user_role,
    validate_profile_invariant,
)
from app.services.clerk_auth import ClerkIdentity, ClerkProfile


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


def utcnow() -> datetime:
    return datetime.now(UTC)


def verified_profile(**overrides: object) -> ClerkProfile:
    values: dict[str, object] = {
        "email": None,
        "email_verified": False,
        "phone": None,
        "phone_verified": False,
        "full_name": None,
    }
    values.update(overrides)
    return ClerkProfile(**values)


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
    assert user.profile_enriched_at is not None


async def test_provision_normalizes_email_before_storage(
    db_session: AsyncSession,
) -> None:
    identity = make_identity(
        email="  Mixed.Case@Example.COM  ",
        email_verified=True,
    )

    user = await provision_user(db_session, identity)

    assert user.email == "mixed.case@example.com"


async def test_provision_is_idempotent(db_session: AsyncSession) -> None:
    identity = make_identity(
        email="repeat@example.com",
        email_verified=True,
        full_name="Repeat User",
    )

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
        email=email.upper(),
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


async def test_provision_rejects_ambiguous_normalized_email(
    db_session: AsyncSession,
) -> None:
    shared = f"{uuid.uuid4().hex}@example.com"
    for email in (shared, shared.upper()):
        user = User(
            full_name="Duplicate",
            email=email,
            password_hash=None,
            role=UserRole.CUSTOMER,
        )
        user.customer = Customer()
        db_session.add(user)
    await db_session.flush()

    with pytest.raises(AccountConflictError):
        await provision_user(
            db_session,
            make_identity(email=shared, email_verified=True),
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


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.TECHNICIAN])
async def test_provision_rejects_privileged_email_auto_linking(
    db_session: AsyncSession,
    role: UserRole,
) -> None:
    email = f"{uuid.uuid4().hex}@example.com"
    existing = User(
        full_name="Privileged",
        email=email,
        password_hash=None,
        role=role,
    )
    if role is UserRole.TECHNICIAN:
        existing.technician = Technician()
    db_session.add(existing)
    await db_session.flush()

    with pytest.raises(AccountConflictError):
        await provision_user(
            db_session,
            make_identity(email=email, email_verified=True),
        )

    assert existing.clerk_user_id is None


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


async def test_validate_profile_invariant_does_not_create_profiles(
    db_session: AsyncSession,
) -> None:
    user = User(
        full_name="Needs Profile",
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(ProfileInvariantError):
        await validate_profile_invariant(db_session, user)

    count = await db_session.scalar(select(func.count(Customer.id)))
    assert count == 0


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


async def test_enrichment_fetches_missing_verified_email(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clerk_user_id = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name=DEFAULT_FULL_NAME,
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    user.customer = Customer()
    db_session.add(user)
    await db_session.flush()

    async def fake_profile(_: str) -> ClerkProfile:
        return verified_profile(
            email=" Enriched@Example.COM ",
            email_verified=True,
            full_name="Enriched Name",
        )

    monkeypatch.setattr(
        "app.services.accounts.fetch_clerk_profile",
        fake_profile,
    )

    updated = await provision_user(
        db_session,
        make_identity(clerk_user_id=clerk_user_id),
    )

    assert updated.email == "enriched@example.com"
    assert updated.full_name == "Enriched Name"
    assert updated.profile_enrichment_attempts == 0
    assert updated.profile_enrichment_last_attempt_at is None
    assert updated.profile_enriched_at is not None


async def test_enrichment_failure_is_bounded_and_backed_off(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clerk_user_id = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name="No Email",
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    user.customer = Customer()
    db_session.add(user)
    await db_session.flush()

    calls: list[str] = []

    async def unavailable(clerk_user_id: str) -> None:
        calls.append(clerk_user_id)

    monkeypatch.setattr(
        "app.services.accounts.fetch_clerk_profile",
        unavailable,
    )

    await provision_user(
        db_session,
        make_identity(clerk_user_id=clerk_user_id),
    )
    await provision_user(
        db_session,
        make_identity(clerk_user_id=clerk_user_id),
    )

    assert calls == [clerk_user_id]
    assert user.email is None
    assert user.profile_enrichment_attempts == 1
    assert user.profile_enrichment_last_attempt_at is not None
    assert user.profile_enriched_at is None


async def test_enrichment_retries_after_backoff(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clerk_user_id = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name="No Email",
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
        profile_enrichment_attempts=1,
        profile_enrichment_last_attempt_at=utcnow() - timedelta(hours=1),
    )
    user.customer = Customer()
    db_session.add(user)
    await db_session.flush()

    async def fake_profile(_: str) -> ClerkProfile:
        return verified_profile(
            email="retry@example.com",
            email_verified=True,
        )

    monkeypatch.setattr(
        "app.services.accounts.fetch_clerk_profile",
        fake_profile,
    )

    updated = await provision_user(
        db_session,
        make_identity(clerk_user_id=clerk_user_id),
    )

    assert updated.email == "retry@example.com"
    assert updated.profile_enrichment_attempts == 0
    assert updated.profile_enriched_at is not None


async def test_enrichment_stops_after_max_attempts(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clerk_user_id = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name="No Email",
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
        profile_enrichment_attempts=MAX_PROFILE_ENRICHMENT_ATTEMPTS,
    )
    user.customer = Customer()
    db_session.add(user)
    await db_session.flush()

    calls: list[str] = []

    async def fake_profile(clerk_user_id: str) -> ClerkProfile:
        calls.append(clerk_user_id)
        return verified_profile(
            email="never@example.com",
            email_verified=True,
        )

    monkeypatch.setattr(
        "app.services.accounts.fetch_clerk_profile",
        fake_profile,
    )

    await provision_user(
        db_session,
        make_identity(clerk_user_id=clerk_user_id),
    )

    assert calls == []
    assert user.email is None


async def test_enrichment_does_not_store_unverified_email(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clerk_user_id = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name="No Email",
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    user.customer = Customer()
    db_session.add(user)
    await db_session.flush()

    async def fake_profile(_: str) -> ClerkProfile:
        return verified_profile(
            email="unverified@example.com",
            email_verified=False,
        )

    monkeypatch.setattr(
        "app.services.accounts.fetch_clerk_profile",
        fake_profile,
    )

    await provision_user(
        db_session,
        make_identity(clerk_user_id=clerk_user_id),
    )

    assert user.email is None
    assert user.profile_enrichment_attempts == 1
    assert user.profile_enriched_at is None


async def test_sync_profile_does_not_overwrite_local_data(
    db_session: AsyncSession,
) -> None:
    clerk_user_id = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name="Local Name",
        email="local@example.com",
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    user.customer = Customer()
    db_session.add(user)
    await db_session.flush()

    updated = await provision_user(
        db_session,
        make_identity(
            clerk_user_id=clerk_user_id,
            email="clerk@example.com",
            email_verified=True,
            full_name="Clerk Name",
        ),
    )

    assert updated.email == "local@example.com"
    assert updated.full_name == "Local Name"
    assert updated.profile_enriched_at is not None


async def test_existing_email_marks_profile_enriched(
    db_session: AsyncSession,
) -> None:
    clerk_user_id = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name="Has Email",
        email="has@example.com",
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    user.customer = Customer()
    db_session.add(user)
    await db_session.flush()

    updated = await provision_user(
        db_session,
        make_identity(clerk_user_id=clerk_user_id),
    )

    assert updated.profile_enriched_at is not None
    assert updated.profile_enrichment_attempts == 0


async def test_operator_link_keeps_role_and_normalizes_email(
    db_session: AsyncSession,
) -> None:
    user = User(
        full_name="Admin",
        email="Admin@Example.COM",
        password_hash=None,
        role=UserRole.ADMIN,
    )
    db_session.add(user)
    await db_session.flush()

    clerk_user_id = f"user_{uuid.uuid4().hex}"
    linked = await link_clerk_identity(
        db_session,
        user,
        clerk_user_id=clerk_user_id,
        profile=verified_profile(
            email="admin@example.com",
            email_verified=True,
        ),
    )

    assert linked.id == user.id
    assert linked.role is UserRole.ADMIN
    assert linked.clerk_user_id == clerk_user_id
    assert linked.email == "admin@example.com"


async def test_operator_link_rejects_mismatched_email(
    db_session: AsyncSession,
) -> None:
    user = User(
        full_name="Technician",
        email="tech@example.com",
        password_hash=None,
        role=UserRole.TECHNICIAN,
    )
    user.technician = Technician()
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(AccountConflictError):
        await link_clerk_identity(
            db_session,
            user,
            clerk_user_id=f"user_{uuid.uuid4().hex}",
            profile=verified_profile(
                email="other@example.com",
                email_verified=True,
            ),
        )

    assert user.clerk_user_id is None


async def test_operator_link_rejects_unverified_clerk_email(
    db_session: AsyncSession,
) -> None:
    user = User(
        full_name="Customer",
        email="customer@example.com",
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    user.customer = Customer()
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(AccountConflictError):
        await link_clerk_identity(
            db_session,
            user,
            clerk_user_id=f"user_{uuid.uuid4().hex}",
            profile=verified_profile(
                email="customer@example.com",
                email_verified=False,
            ),
        )


async def test_operator_link_rejects_already_linked_account(
    db_session: AsyncSession,
) -> None:
    user = User(
        full_name="Customer",
        email="linked@example.com",
        clerk_user_id=f"user_{uuid.uuid4().hex}",
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    user.customer = Customer()
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(AccountConflictError):
        await link_clerk_identity(
            db_session,
            user,
            clerk_user_id=f"user_{uuid.uuid4().hex}",
            profile=verified_profile(
                email="linked@example.com",
                email_verified=True,
            ),
        )


async def test_operator_link_rejects_identity_used_elsewhere(
    db_session: AsyncSession,
) -> None:
    clerk_user_id = f"user_{uuid.uuid4().hex}"
    other = User(
        full_name="Other",
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    other.customer = Customer()
    user = User(
        full_name="Customer",
        email="available@example.com",
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    user.customer = Customer()
    db_session.add_all([other, user])
    await db_session.flush()

    with pytest.raises(AccountConflictError):
        await link_clerk_identity(
            db_session,
            user,
            clerk_user_id=clerk_user_id,
            profile=verified_profile(
                email="available@example.com",
                email_verified=True,
            ),
        )
