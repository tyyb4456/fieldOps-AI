from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def canonical_symptoms(values: Any) -> list[str]:
    """Return a stable, deduplicated representation of symptom text."""

    if not isinstance(values, (list, tuple)):
        return []
    normalized = {
        str(item).strip()
        for item in values
        if str(item).strip()
    }
    return sorted(normalized, key=str.casefold)


def canonical_json(value: Any) -> str:
    """Serialize a value deterministically for hashing."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def canonical_digest(value: Any) -> str:
    """Return the SHA-256 hex digest of canonical JSON."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def digest_records(records: Sequence[Mapping[str, Any]]) -> str:
    """Return one digest over an ordered sequence of record payloads."""

    return canonical_digest(list(records))


__all__ = [
    "canonical_digest",
    "canonical_json",
    "canonical_symptoms",
    "digest_records",
]
