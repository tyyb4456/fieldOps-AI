from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from clerk_backend_api import Clerk
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions
from starlette.requests import Request

from app.core.config import settings
from app.services.shared.email import normalize_email

logger = logging.getLogger(__name__)

SESSION_TOKEN_TYPE = "session_token"


class ClerkConfigurationError(RuntimeError):
    """Raised when Clerk verification is not configured."""


class ClerkAuthenticationError(Exception):
    """Raised when a Clerk session token cannot be verified."""

    def __init__(self, reason: str | None = None) -> None:
        super().__init__("Invalid or missing authentication credentials")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ClerkProfile:
    email: str | None = None
    email_verified: bool = False
    phone: str | None = None
    phone_verified: bool = False
    full_name: str | None = None


@dataclass(frozen=True, slots=True)
class ClerkIdentity:
    clerk_user_id: str
    session_id: str | None
    claims: Mapping[str, Any]
    profile: ClerkProfile


class _BearerOnlyRequest:
    """Minimal request view containing only a Bearer Authorization header.

    ``authenticate_request`` falls back to the ``__session`` cookie whenever
    no Authorization header is present. FieldOps deliberately uses Bearer-only
    API authentication, so the SDK is given a view that cannot see cookies.
    This uses the documented Requestish protocol rather than re-implementing
    token verification.
    """

    __slots__ = ("headers",)

    def __init__(self, token: str) -> None:
        self.headers: Mapping[str, str] = {
            "Authorization": f"Bearer {token}",
        }


def _extract_bearer_token(request: Request) -> str:
    header = request.headers.get("authorization")
    if header is None:
        raise ClerkAuthenticationError("bearer-token-missing")

    scheme, separator, token = header.partition(" ")
    if separator != " " or scheme.lower() != "bearer":
        raise ClerkAuthenticationError("unsupported-authorization-scheme")

    token = token.strip()
    if not token:
        raise ClerkAuthenticationError("bearer-token-missing")
    if " " in token:
        raise ClerkAuthenticationError("malformed-bearer-token")
    return token


def _first_string(
    payload: Mapping[str, Any],
    *keys: str,
) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _claim_is_true(payload: Mapping[str, Any], *keys: str) -> bool:
    return any(payload.get(key) is True for key in keys)


def identity_from_payload(payload: Mapping[str, Any]) -> ClerkIdentity:
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise ClerkAuthenticationError("missing-subject")

    session_id = payload.get("sid")
    if not isinstance(session_id, str) or not session_id.strip():
        session_id = None

    first_name = _first_string(payload, "first_name", "given_name")
    last_name = _first_string(payload, "last_name", "family_name")
    full_name = _first_string(payload, "name", "full_name")
    if full_name is None and (first_name or last_name):
        full_name = " ".join(
            part for part in (first_name, last_name) if part
        )

    return ClerkIdentity(
        clerk_user_id=subject.strip(),
        session_id=session_id,
        claims=dict(payload),
        profile=ClerkProfile(
            email=normalize_email(
                _first_string(
                    payload,
                    "email",
                    "email_address",
                    "primary_email_address",
                )
            ),
            email_verified=_claim_is_true(
                payload,
                "email_verified",
                "primary_email_address_verified",
            ),
            phone=_first_string(
                payload,
                "phone",
                "phone_number",
                "primary_phone_number",
            ),
            phone_verified=_claim_is_true(
                payload,
                "phone_verified",
                "phone_number_verified",
                "primary_phone_number_verified",
            ),
            full_name=full_name,
        ),
    )


def verify_clerk_token(
    request: Request,
    *,
    secret_key: str | None = None,
    jwt_key: str | None = None,
    authorized_parties: list[str] | None = None,
) -> ClerkIdentity:
    resolved_secret = (
        secret_key if secret_key is not None else settings.clerk_secret_key
    )
    resolved_jwt_key = (
        jwt_key if jwt_key is not None else settings.clerk_jwt_key
    )
    resolved_parties = (
        authorized_parties
        if authorized_parties is not None
        else settings.clerk_authorized_parties_list
    )

    if not resolved_secret and not resolved_jwt_key:
        raise ClerkConfigurationError(
            "Clerk authentication is not configured"
        )

    bearer_token = _extract_bearer_token(request)

    state = authenticate_request(
        _BearerOnlyRequest(bearer_token),
        AuthenticateRequestOptions(
            secret_key=resolved_secret,
            jwt_key=resolved_jwt_key,
            # An explicitly empty list must reject every token rather than
            # disabling authorized-party validation. Never use `or None` here.
            authorized_parties=resolved_parties,
            accepts_token=[SESSION_TOKEN_TYPE],
        ),
    )

    if not state.is_signed_in or state.payload is None:
        reason = None
        if state.reason is not None and state.reason.value:
            reason = state.reason.value[0]
        raise ClerkAuthenticationError(reason)

    return identity_from_payload(state.payload)


def _primary_email(user: Any) -> tuple[str | None, bool]:
    primary_id = getattr(user, "primary_email_address_id", None)
    addresses = getattr(user, "email_addresses", None) or []
    primary = next(
        (address for address in addresses if address.id == primary_id),
        None,
    )

    verified_candidates = []
    for address in addresses:
        verification = getattr(address, "verification", None)
        if getattr(verification, "status", None) == "verified":
            verified_candidates.append(address)

    if primary is not None:
        verification = getattr(primary, "verification", None)
        if getattr(verification, "status", None) == "verified":
            return normalize_email(primary.email_address), True

    if verified_candidates:
        return normalize_email(verified_candidates[0].email_address), True

    if primary is not None:
        return normalize_email(primary.email_address), False

    return None, False


def _primary_phone(user: Any) -> tuple[str | None, bool]:
    primary_id = getattr(user, "primary_phone_number_id", None)
    numbers = getattr(user, "phone_numbers", None) or []
    primary = next(
        (number for number in numbers if number.id == primary_id),
        None,
    )

    verified_candidates = []
    for number in numbers:
        verification = getattr(number, "verification", None)
        if getattr(verification, "status", None) == "verified":
            verified_candidates.append(number)

    if primary is not None:
        verification = getattr(primary, "verification", None)
        if getattr(verification, "status", None) == "verified":
            return primary.phone_number, True

    if verified_candidates:
        return verified_candidates[0].phone_number, True

    if primary is not None:
        return primary.phone_number, False

    return None, False


async def fetch_clerk_profile(
    clerk_user_id: str,
) -> ClerkProfile | None:
    """Fetch a Clerk profile, returning None when the lookup is unavailable.

    ``None`` means the Backend API could not be reached or returned an
    unexpected response. A non-None profile may still have no verified email;
    callers must inspect ``email_verified`` before storing identity fields.
    """
    if not settings.clerk_secret_key:
        return None

    try:
        async with Clerk(bearer_auth=settings.clerk_secret_key) as clerk:
            user = await clerk.users.get_async(user_id=clerk_user_id)
    except Exception:  # noqa: BLE001 - profile enrichment is best-effort
        logger.warning(
            "Unable to fetch Clerk profile for identity enrichment",
            extra={"clerk_user_id": clerk_user_id},
            exc_info=False,
        )
        return None

    first_name = getattr(user, "first_name", None)
    last_name = getattr(user, "last_name", None)
    username = getattr(user, "username", None)
    full_name = " ".join(
        part for part in (first_name, last_name) if part
    ) or username

    email, email_verified = _primary_email(user)
    phone, phone_verified = _primary_phone(user)

    return ClerkProfile(
        email=email,
        email_verified=email_verified,
        phone=phone,
        phone_verified=phone_verified,
        full_name=full_name or None,
    )
