from __future__ import annotations

import logging
import uuid
from dataclasses import replace

from sqlalchemy import func, inspect as sa_inspect, select
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
from app.services.clerk_auth import (
    ClerkIdentity,
    ClerkProfile,
    fetch_clerk_profile,
)

logger = logging.getLogger(__name__)

DEFAULT_FULL_NAME = "FieldOps User"


class AccountConflictError(Exception):
    """Raised when a verified identity conflicts with another account."""


class ProfileInvariantError(Exception):
    """Raised when a user's role and operational profile disagree."""


class AccountNotFoundError(Exception):
    """Raised when a requested account does not exist."""


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


async def _find_by_email(
    session: AsyncSession,
    email: str,
) -> User | None:
    result = await session.execute(
        select(User)
        .options(*_user_load_options())
        .where(User.email == email)
    )
    return result.scalar_one_or_none()


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


async def _resolve_profile(identity: ClerkIdentity) -> ClerkProfile:
    profile = identity.profile
    if profile.email and profile.email_verified:
        return profile

    fetched = await fetch_clerk_profile(identity.clerk_user_id)
    if fetched is None:
        return profile

    return ClerkProfile(
        email=fetched.email or profile.email,
        email_verified=fetched.email_verified or profile.email_verified,
        phone=fetched.phone or profile.phone,
        phone_verified=fetched.phone_verified or profile.phone_verified,
        full_name=fetched.full_name or profile.full_name,
    )


async def _assert_no_identity_conflicts(
    session: AsyncSession,
    identity: ClerkIdentity,
    *,
    exclude_user_id: uuid.UUID | None = None,
) -> None:
    profile = identity.profile

    if profile.email and profile.email_verified:
        existing = await _find_by_email(session, profile.email)
        if existing is not None and existing.id != exclude_user_id:
            raise AccountConflictError(
                "A different account already uses this email address"
            )

    if profile.phone and profile.phone_verified:
        existing = await _find_by_phone(session, profile.phone)
        if existing is not None and existing.id != exclude_user_id:
            raise AccountConflictError(
                "A different account already uses this phone number"
            )


def _fallback_full_name(profile: ClerkProfile) -> str:
    if profile.full_name:
        return profile.full_name
    if profile.email:
        local_part = profile.email.split("@", 1)[0].strip()
        if local_part:
            return local_part
    return DEFAULT_FULL_NAME


async def _sync_profile(
    session: AsyncSession,
    user: User,
    identity: ClerkIdentity,
) -> None:
    profile = identity.profile

    if profile.full_name and user.full_name == DEFAULT_FULL_NAME:
        user.full_name = profile.full_name

    if (
        user.email is None
        and profile.email
        and profile.email_verified
    ):
        await _assert_no_identity_conflicts(
            session,
            identity,
            exclude_user_id=user.id,
        )
        user.email = profile.email

    if (
        user.phone is None
        and profile.phone
        and profile.phone_verified
    ):
        await _assert_no_identity_conflicts(
            session,
            identity,
            exclude_user_id=user.id,
        )
        user.phone = profile.phone


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
) -> User:
    profile = identity.profile
    await _assert_no_identity_conflicts(session, identity)

    user = User(
        full_name=_fallback_full_name(profile),
        email=profile.email if profile.email_verified else None,
        phone=profile.phone if profile.phone_verified else None,
        clerk_user_id=identity.clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
        is_active=True,
    )
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
        await ensure_profile_invariant(session, user)
        return user

    profile = await _resolve_profile(identity)
    if profile is not identity.profile:
        identity = replace(identity, profile=profile)

    user = await _find_by_email(
        session,
        identity.profile.email,
    ) if (
        identity.profile.email
        and identity.profile.email_verified
    ) else None

    if user is not None:
        if (
            user.clerk_user_id is not None
            and user.clerk_user_id != identity.clerk_user_id
        ):
            raise AccountConflictError(
                "This email address is already linked to another identity"
            )
        user.clerk_user_id = identity.clerk_user_id
        await _sync_profile(session, user, identity)
        await ensure_profile_invariant(session, user)
        return user

    return await _create_user(session, identity)


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
        user = await _find_by_clerk_id(session, identity.clerk_user_id)
        if user is None:
            raise AccountConflictError(
                "The account could not be provisioned due to a "
                "conflicting identity"
            ) from exc
        await _sync_profile(session, user, identity)
        await ensure_profile_invariant(session, user)
        await session.commit()
        return user
    except Exception:
        await session.rollback()
        raise


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
