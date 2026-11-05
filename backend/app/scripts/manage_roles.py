"""Controlled role provisioning for privileged accounts.

Clerk owns authentication only. Application roles are assigned here, in the
backend database, after an operator has verified the person out-of-band.

Usage:
    python -m app.scripts.manage_roles set-role --email user@example.com \\
        --role admin
    python -m app.scripts.manage_roles set-role --user-id <uuid> \\
        --role technician

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
    set_user_role,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assign an application role to a provisioned user.",
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

    return parser


async def _run(args: argparse.Namespace) -> int:
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
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        await dispose_engine()

    print(f"Updated user role to {role.value}.")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
