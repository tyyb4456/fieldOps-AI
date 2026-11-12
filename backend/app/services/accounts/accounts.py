from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.complaint import Complaint
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.equipment import Equipment
from app.models.service_record import ServiceRecord
from app.models.technician import Technician
from app.models.technician_assignment import TechnicianAssignment
from app.models.user import User
from app.services.accounts.clerk_auth import (
    ClerkIdentity,
    ClerkProfile,
    fetch_clerk_profile,
)
from app.services.shared.email import normalize_email

logger = logging.getLogger(__name__)

DEFAULT_FULL_NAME = "FieldOps User"
PUBLIC_LINKABLE_ROLES = frozenset({UserRole.CUSTOMER})

MAX_PROFILE_ENRICHMENT_ATTEMPTS = 5
PROFILE_ENRICHMENT_BASE_BACKOFF_SECONDS = 15 * 60
PROFILE_ENRICHMENT_MAX_BACKOFF_SECONDS = 24 * 60 * 60


class AccountConflictError(Exception):
    """Raised when a verified identity conflicts with another account."""


class ProfileInvariantError(Exception):
    """Raised when a user's role and operational profile disagree."""


class AccountNotFoundError(Exception):
    """Raised when a requested account does not exist."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _user_load_options() -> tuple:
    return (
        selectinload(User.customer),
        selectinload(User.technician),
    )


async def _find_by_clerk_id(
    session: AsyncSession,
    clerk_user_id: str,
) -> User | None:
    result = await session.execute(
        select(User)
        .options(*_user_load_options())
        .where(User.clerk_user_id == clerk_user_id)
    )
    return result.scalar_one_or_none()


async def find_user_by_clerk_id(
    session: AsyncSession,
    clerk_user_id: str,
) -> User | None:
    return await _find_by_clerk_id(session, clerk_user_id)


async def _find_by_email(
    session: AsyncSession,
    email: str,
) -> User | None:
    normalized = normalize_email(email)
    if normalized is None:
        return None

    result = await session.execute(
        select(User)
        .options(*_user_load_options())
        .where(func.lower(func.trim(User.email)) == normalized)
        .limit(2)
    )
    users = list(result.scalars().all())
    if len(users) > 1:
        raise AccountConflictError(
            "Multiple local accounts share this email address; "
            "operator resolution is required"
        )
    return users[0] if users else None


async def _find_by_phone(
    session: AsyncSession,
    phone: str,
) -> User | None:
    result = await session.execute(
        select(User)
        .options(*_user_load_options())
        .where(User.phone == phone)
    )
    return result.scalar_one_or_none()


def _merge_profiles(
    token_profile: ClerkProfile,
    fetched: ClerkProfile,
) -> ClerkProfile:
    if fetched.email and fetched.email_verified:
        email = normalize_email(fetched.email)
        email_verified = True
    elif token_profile.email and token_profile.email_verified:
        email = normalize_email(token_profile.email)
        email_verified = True
    elif fetched.email:
        email = normalize_email(fetched.email)
        email_verified = fetched.email_verified
    else:
        email = normalize_email(token_profile.email)
        email_verified = token_profile.email_verified

    phone: str | None
    if fetched.phone and fetched.phone_verified:
        phone = fetched.phone
        phone_verified = True
    elif token_profile.phone and token_profile.phone_verified:
        phone = token_profile.phone
        phone_verified = True
    elif fetched.phone:
        phone = fetched.phone
        phone_verified = fetched.phone_verified
    else:
        phone = token_profile.phone
        phone_verified = token_profile.phone_verified

    return ClerkProfile(
        email=email,
        email_verified=email_verified,
        phone=phone,
        phone_verified=phone_verified,
        full_name=fetched.full_name or token_profile.full_name,
    )


async def _resolve_profile(
    identity: ClerkIdentity,
) -> tuple[ClerkProfile, bool]:
    """Resolve a profile for a new account.

    Returns the resolved profile and whether a Clerk Backend API lookup was
    attempted. Returning the flag allows the caller to record a bounded
    enrichment attempt when the API is temporarily unavailable.
    """
    profile = identity.profile
    if profile.email and profile.email_verified:
        return profile, False

    fetched = await fetch_clerk_profile(identity.clerk_user_id)
    if fetched is None:
        return profile, True

    return _merge_profiles(profile, fetched), True


async def _assert_email_available(
    session: AsyncSession,
    email: str,
    *,
    exclude_user_id: uuid.UUID | None = None,
) -> None:
    existing = await _find_by_email(session, email)
    if existing is not None and existing.id != exclude_user_id:
        raise AccountConflictError(
            "A different account already uses this email address"
        )


async def _assert_phone_available(
    session: AsyncSession,
    phone: str,
    *,
    exclude_user_id: uuid.UUID | None = None,
) -> None:
    existing = await _find_by_phone(session, phone)
    if existing is not None and existing.id != exclude_user_id:
        raise AccountConflictError(
            "A different account already uses this phone number"
        )


async def _assert_no_identity_conflicts(
    session: AsyncSession,
    identity: ClerkIdentity,
    *,
    exclude_user_id: uuid.UUID | None = None,
) -> None:
    profile = identity.profile

    if profile.email and profile.email_verified:
        await _assert_email_available(
            session,
            profile.email,
            exclude_user_id=exclude_user_id,
        )

    if profile.phone and profile.phone_verified:
        await _assert_phone_available(
            session,
            profile.phone,
            exclude_user_id=exclude_user_id,
        )


def _fallback_full_name(profile: ClerkProfile) -> str:
    if profile.full_name:
        return profile.full_name
    if profile.email:
        local_part = profile.email.split("@", 1)[0].strip()
        if local_part:
            return local_part
    return DEFAULT_FULL_NAME


async def _apply_verified_profile(
    session: AsyncSession,
    user: User,
    profile: ClerkProfile,
) -> bool:
    """Apply verified Clerk identity fields without overwriting local data.

    Returns True when a verified email is present on the account afterwards.
    """
    if profile.full_name and user.full_name == DEFAULT_FULL_NAME:
        user.full_name = profile.full_name

    if user.email is not None:
        normalized_existing = normalize_email(user.email)
        if (
            normalized_existing is not None
            and normalized_existing != user.email
        ):
            await _assert_email_available(
                session,
                normalized_existing,
                exclude_user_id=user.id,
            )
            user.email = normalized_existing

    if (
        user.email is None
        and profile.email
        and profile.email_verified
    ):
        normalized = normalize_email(profile.email)
        if normalized is not None:
            await _assert_email_available(
                session,
                normalized,
                exclude_user_id=user.id,
            )
            user.email = normalized

    if (
        user.phone is None
        and profile.phone
        and profile.phone_verified
    ):
        await _assert_phone_available(
            session,
            profile.phone,
            exclude_user_id=user.id,
        )
        user.phone = profile.phone

    return bool(user.email)


async def _sync_profile(
    session: AsyncSession,
    user: User,
    identity: ClerkIdentity,
) -> None:
    applied = await _apply_verified_profile(
        session,
        user,
        identity.profile,
    )
    if applied:
        _mark_profile_enriched(user, _utcnow())


def _need_profile_enrichment(user: User) -> bool:
    return not user.email


def _enrichment_backoff(attempts: int) -> timedelta:
    if attempts <= 0:
        return timedelta(0)
    exponent = min(attempts - 1, 10)
    seconds = min(
        PROFILE_ENRICHMENT_BASE_BACKOFF_SECONDS * (2**exponent),
        PROFILE_ENRICHMENT_MAX_BACKOFF_SECONDS,
    )
    return timedelta(seconds=seconds)


def _can_attempt_enrichment(user: User, now: datetime) -> bool:
    if user.profile_enrichment_attempts >= MAX_PROFILE_ENRICHMENT_ATTEMPTS:
        return False
    last_attempt = user.profile_enrichment_last_attempt_at
    if last_attempt is None:
        return True
    return (
        now - _as_utc(last_attempt)
        >= _enrichment_backoff(user.profile_enrichment_attempts)
    )


def _record_enrichment_attempt(user: User, now: datetime) -> None:
    user.profile_enrichment_attempts += 1
    user.profile_enrichment_last_attempt_at = now


def _mark_profile_enriched(user: User, now: datetime) -> None:
    user.profile_enriched_at = now
    user.profile_enrichment_attempts = 0
    user.profile_enrichment_last_attempt_at = None


async def _maybe_enrich_profile(
    session: AsyncSession,
    user: User,
    identity: ClerkIdentity,
) -> None:
    if not _need_profile_enrichment(user):
        if user.profile_enriched_at is None:
            _mark_profile_enriched(user, _utcnow())
        return

    now = _utcnow()
    if not _can_attempt_enrichment(user, now):
        return

    _record_enrichment_attempt(user, now)
    fetched = await fetch_clerk_profile(
        user.clerk_user_id or identity.clerk_user_id
    )
    if fetched is None:
        logger.info(
            "Clerk profile enrichment deferred",
            extra={
                "user_id": str(user.id),
                "attempts": user.profile_enrichment_attempts,
            },
        )
        return

    merged = _merge_profiles(identity.profile, fetched)
    applied = await _apply_verified_profile(session, user, merged)
    if applied:
        _mark_profile_enriched(user, now)
        logger.info(
            "Clerk profile enrichment completed",
            extra={
                "user_id": str(user.id),
                "attempts": user.profile_enrichment_attempts,
            },
        )
    else:
        logger.info(
            "Clerk profile has no verified email; enrichment remains pending",
            extra={
                "user_id": str(user.id),
                "attempts": user.profile_enrichment_attempts,
            },
        )


def _raise_profile_invariant(user: User, detail: str) -> None:
    raise ProfileInvariantError(
        f"User {user.id} has an invalid role/profile combination: {detail}"
    )


async def _ensure_profiles_loaded(
    session: AsyncSession,
    user: User,
) -> None:
    state = sa_inspect(user)
    missing = [
        name
        for name in ("customer", "technician")
        if name not in state.dict
    ]
    if not missing:
        return

    if user.id is None:
        for name in missing:
            setattr(user, name, None)
        return

    await session.refresh(user, missing)


async def validate_profile_invariant(
    session: AsyncSession,
    user: User,
) -> None:
    """Validate role/profile consistency without creating or modifying rows."""
    await _ensure_profiles_loaded(session, user)

    if user.role == UserRole.CUSTOMER:
        if user.technician is not None:
            _raise_profile_invariant(
                user,
                "customer role with a technician profile",
            )
        if user.customer is None:
            _raise_profile_invariant(
                user,
                "customer role without a customer profile",
            )
        return

    if user.role == UserRole.TECHNICIAN:
        if user.customer is not None:
            _raise_profile_invariant(
                user,
                "technician role with a customer profile",
            )
        if user.technician is None:
            _raise_profile_invariant(
                user,
                "technician role without a technician profile",
            )
        return

    if user.role == UserRole.ADMIN:
        if user.customer is not None or user.technician is not None:
            _raise_profile_invariant(
                user,
                "admin role with an operational profile",
            )
        return

    _raise_profile_invariant(user, f"unsupported role {user.role!r}")


async def ensure_profile_invariant(
    session: AsyncSession,
    user: User,
) -> None:
    await _ensure_profiles_loaded(session, user)

    if user.role == UserRole.CUSTOMER:
        if user.technician is not None:
            _raise_profile_invariant(
                user,
                "customer role with a technician profile",
            )
        if user.customer is None:
            user.customer = Customer()
            session.add(user.customer)
        return

    if user.role == UserRole.TECHNICIAN:
        if user.customer is not None:
            _raise_profile_invariant(
                user,
                "technician role with a customer profile",
            )
        if user.technician is None:
            user.technician = Technician()
            session.add(user.technician)
        return

    if user.role == UserRole.ADMIN:
        if user.customer is not None or user.technician is not None:
            _raise_profile_invariant(
                user,
                "admin role with an operational profile",
            )
        return

    _raise_profile_invariant(user, f"unsupported role {user.role!r}")


async def _create_user(
    session: AsyncSession,
    identity: ClerkIdentity,
    *,
    enrichment_attempted: bool,
) -> User:
    profile = identity.profile
    await _assert_no_identity_conflicts(session, identity)

    now = _utcnow()
    email = (
        normalize_email(profile.email)
        if profile.email_verified
        else None
    )
    user = User(
        full_name=_fallback_full_name(profile),
        email=email,
        phone=profile.phone if profile.phone_verified else None,
        clerk_user_id=identity.clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    if user.email is not None:
        user.profile_enriched_at = now
    elif enrichment_attempted:
        user.profile_enrichment_attempts = 1
        user.profile_enrichment_last_attempt_at = now

    user.customer = Customer()
    user.technician = None
    session.add(user)
    return user


async def _provision(
    session: AsyncSession,
    identity: ClerkIdentity,
) -> User:
    user = await _find_by_clerk_id(session, identity.clerk_user_id)

    if user is not None:
        await _sync_profile(session, user, identity)
        await _maybe_enrich_profile(session, user, identity)
        await ensure_profile_invariant(session, user)
        return user

    profile, enrichment_attempted = await _resolve_profile(identity)
    if profile is not identity.profile:
        identity = replace(identity, profile=profile)

    user = (
        await _find_by_email(session, identity.profile.email)
        if identity.profile.email and identity.profile.email_verified
        else None
    )

    if user is not None:
        if user.role not in PUBLIC_LINKABLE_ROLES:
            logger.warning(
                "Rejected automatic Clerk linking for privileged account",
                extra={
                    "user_id": str(user.id),
                    "role": user.role.value,
                    "clerk_user_id": identity.clerk_user_id,
                },
            )
            raise AccountConflictError(
                "Privileged accounts require explicit operator linking"
            )

        if (
            user.clerk_user_id is not None
            and user.clerk_user_id != identity.clerk_user_id
        ):
            raise AccountConflictError(
                "This email address is already linked to another identity"
            )

        user.clerk_user_id = identity.clerk_user_id
        await _sync_profile(session, user, identity)
        await _maybe_enrich_profile(session, user, identity)
        await ensure_profile_invariant(session, user)
        _mark_profile_enriched(user, _utcnow())
        logger.info(
            "Linked local account to Clerk identity",
            extra={
                "user_id": str(user.id),
                "role": user.role.value,
                "clerk_user_id": identity.clerk_user_id,
                "link_source": "verified_email",
            },
        )
        return user

    return await _create_user(
        session,
        identity,
        enrichment_attempted=enrichment_attempted,
    )


async def provision_user(
    session: AsyncSession,
    identity: ClerkIdentity,
) -> User:
    """Provision or update a user without committing the transaction."""
    return await _provision(session, identity)


async def get_or_provision_user(
    session: AsyncSession,
    identity: ClerkIdentity,
) -> User:
    try:
        user = await _provision(session, identity)
        await session.commit()
        return user
    except IntegrityError as exc:
        await session.rollback()
        existing_user = await _find_by_clerk_id(
            session,
            identity.clerk_user_id,
        )
        if existing_user is None:
            raise AccountConflictError(
                "The account could not be provisioned due to a "
                "conflicting identity"
            ) from exc
        await _sync_profile(session, existing_user, identity)
        await _maybe_enrich_profile(session, existing_user, identity)
        await ensure_profile_invariant(session, existing_user)
        await session.commit()
        return existing_user
    except Exception:
        await session.rollback()
        raise


async def link_clerk_identity(
    session: AsyncSession,
    user: User,
    *,
    clerk_user_id: str,
    profile: ClerkProfile,
) -> User:
    """Explicitly link an operator-verified local account to Clerk.

    The caller is responsible for verifying the Clerk identity out-of-band and
    obtaining its profile. This operation never changes the user's role.
    """
    normalized_profile_email = normalize_email(profile.email)
    normalized_user_email = normalize_email(user.email)

    if not normalized_profile_email or not profile.email_verified:
        raise AccountConflictError(
            "The Clerk identity does not have a verified email address"
        )
    if normalized_user_email is None:
        raise AccountConflictError(
            "The local account has no email address to verify against"
        )
    if normalized_user_email != normalized_profile_email:
        raise AccountConflictError(
            "The Clerk verified email does not match the local account"
        )
    if (
        user.clerk_user_id is not None
        and user.clerk_user_id != clerk_user_id
    ):
        raise AccountConflictError(
            "The local account is already linked to a different "
            "Clerk identity"
        )

    existing = await _find_by_clerk_id(session, clerk_user_id)
    if existing is not None and existing.id != user.id:
        raise AccountConflictError(
            "The Clerk identity is already linked to another local account"
        )

    user.clerk_user_id = clerk_user_id
    await _apply_verified_profile(session, user, profile)
    _mark_profile_enriched(user, _utcnow())
    logger.info(
        "Operator linked local account to Clerk identity",
        extra={
            "user_id": str(user.id),
            "role": user.role.value,
            "clerk_user_id": clerk_user_id,
            "link_source": "operator",
        },
    )
    return user


async def _count_customer_dependents(
    session: AsyncSession,
    customer_id: uuid.UUID,
) -> int:
    equipment_count = await session.scalar(
        select(func.count())
        .select_from(Equipment)
        .where(Equipment.customer_id == customer_id)
    )
    complaint_count = await session.scalar(
        select(func.count())
        .select_from(Complaint)
        .where(Complaint.customer_id == customer_id)
    )
    return int(equipment_count or 0) + int(complaint_count or 0)


async def _count_technician_dependents(
    session: AsyncSession,
    technician_id: uuid.UUID,
) -> int:
    assignment_count = await session.scalar(
        select(func.count())
        .select_from(TechnicianAssignment)
        .where(TechnicianAssignment.technician_id == technician_id)
    )
    service_count = await session.scalar(
        select(func.count())
        .select_from(ServiceRecord)
        .where(ServiceRecord.technician_id == technician_id)
    )
    return int(assignment_count or 0) + int(service_count or 0)


async def _remove_empty_profile(
    session: AsyncSession,
    user: User,
    *,
    role: UserRole,
) -> None:
    if role == UserRole.CUSTOMER and user.customer is not None:
        dependents = await _count_customer_dependents(
            session,
            user.customer.id,
        )
        if dependents:
            raise ProfileInvariantError(
                "Cannot remove a customer profile that owns operational data"
            )
        await session.delete(user.customer)
        user.customer = None
        return

    if role == UserRole.TECHNICIAN and user.technician is not None:
        dependents = await _count_technician_dependents(
            session,
            user.technician.id,
        )
        if dependents:
            raise ProfileInvariantError(
                "Cannot remove a technician profile that owns operational data"
            )
        await session.delete(user.technician)
        user.technician = None


async def get_user_by_id(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> User:
    result = await session.execute(
        select(User)
        .options(*_user_load_options())
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise AccountNotFoundError(f"User {user_id} does not exist")
    return user


async def get_user_by_email(
    session: AsyncSession,
    email: str,
) -> User:
    user = await _find_by_email(session, email)
    if user is None:
        raise AccountNotFoundError(f"User {email} does not exist")
    return user


async def set_user_role(
    session: AsyncSession,
    user: User,
    role: UserRole,
) -> User:
    await _ensure_profiles_loaded(session, user)

    if user.role == role:
        await ensure_profile_invariant(session, user)
        return user

    if role == UserRole.CUSTOMER:
        await _remove_empty_profile(
            session,
            user,
            role=UserRole.TECHNICIAN,
        )
    elif role == UserRole.TECHNICIAN:
        await _remove_empty_profile(
            session,
            user,
            role=UserRole.CUSTOMER,
        )
    elif role == UserRole.ADMIN:
        await _remove_empty_profile(
            session,
            user,
            role=UserRole.CUSTOMER,
        )
        await _remove_empty_profile(
            session,
            user,
            role=UserRole.TECHNICIAN,
        )

    user.role = role
    await ensure_profile_invariant(session, user)
    return user
