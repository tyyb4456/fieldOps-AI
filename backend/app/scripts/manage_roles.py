"""Controlled role provisioning for privileged accounts.

Clerk owns authentication only. Application roles are assigned here, in the
backend database, after an operator has verified the person out-of-band.

Usage:
    python -m app.scripts.manage_roles set-role --email user@example.com \\
        --role admin
    python -m app.scripts.manage_roles set-role --user-id <uuid> \\
        --role technician
    python -m app.scripts.manage_roles link-identity --email user@example.com \\
        --clerk-user-id user_xxx

This command never reads Clerk metadata and never trusts frontend input.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from app.db.session import async_session_factory, dispose_engine
from app.models.enums import UserRole
from app.services.accounts import (
    AccountConflictError,
    AccountNotFoundError,
    ProfileInvariantError,
    get_user_by_email,
    get_user_by_id,
    link_clerk_identity,
    set_user_role,
)
from app.services.clerk_auth import fetch_clerk_profile


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assign an application role or link a Clerk identity to a "
            "provisioned user."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    set_role = subparsers.add_parser(
        "set-role",
        help="Change a user's application role.",
    )
    identity = set_role.add_mutually_exclusive_group(required=True)
    identity.add_argument("--user-id", type=uuid.UUID)
    identity.add_argument("--email")
    set_role.add_argument(
        "--role",
        required=True,
        choices=[role.value for role in UserRole],
    )

    link_identity = subparsers.add_parser(
        "link-identity",
        help=(
            "Explicitly bind an existing local account to a Clerk identity "
            "without changing its role."
        ),
    )
    link_target = link_identity.add_mutually_exclusive_group(required=True)
    link_target.add_argument("--user-id", type=uuid.UUID)
    link_target.add_argument("--email")
    link_identity.add_argument(
        "--clerk-user-id",
        required=True,
        help="Clerk user ID (user_...) verified by the operator.",
    )

    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.command == "link-identity":
        return await _link_identity(args)

    role = UserRole(args.role)

    try:
        async with async_session_factory() as session:
            if args.user_id is not None:
                user = await get_user_by_id(session, args.user_id)
            else:
                user = await get_user_by_email(session, args.email)
            await set_user_role(session, user, role)
            await session.commit()
    except (
        AccountConflictError,
        AccountNotFoundError,
        ProfileInvariantError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI reports unexpected errors
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        await dispose_engine()

    print(f"Updated user role to {role.value}.")
    return 0


async def _link_identity(args: argparse.Namespace) -> int:
    try:
        profile = await fetch_clerk_profile(args.clerk_user_id)
        if profile is None:
            print(
                "error: unable to verify the Clerk identity. Check "
                "CLERK_SECRET_KEY and network connectivity.",
                file=sys.stderr,
            )
            return 1

        async with async_session_factory() as session:
            if args.user_id is not None:
                user = await get_user_by_id(session, args.user_id)
            else:
                user = await get_user_by_email(session, args.email)
            await link_clerk_identity(
                session,
                user,
                clerk_user_id=args.clerk_user_id,
                profile=profile,
            )
            await session.commit()
    except (
        AccountConflictError,
        AccountNotFoundError,
        ProfileInvariantError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI reports unexpected errors
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        await dispose_engine()

    print("Linked local account to the verified Clerk identity.")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
