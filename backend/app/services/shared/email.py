from __future__ import annotations


def normalize_email(value: str | None) -> str | None:
    """Return a consistent email representation for storage and lookup.

    Email addresses are compared case-insensitively and without surrounding
    whitespace. The local part of an address is technically case-sensitive in
    the SMTP specification, but virtually every identity provider and mail
    system treats it as case-insensitive. Clerk normalizes addresses as well,
    so FieldOps must use the same policy everywhere.
    """
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None
