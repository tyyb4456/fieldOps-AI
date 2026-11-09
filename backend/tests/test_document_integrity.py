from __future__ import annotations

import hashlib

import pytest

from app.services.document_ingestion import (
    is_valid_sha256,
    validate_upload,
)
from tests.pdf_factory import build_pdf


def test_valid_lowercase_sha256_is_accepted() -> None:
    assert is_valid_sha256("a" * 64)
    assert is_valid_sha256(hashlib.sha256(b"content").hexdigest())


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        " " + "a" * 63,
        "a" * 63 + "\n",
    ],
)
def test_invalid_sha256_is_rejected(value: str | None) -> None:
    assert not is_valid_sha256(value)


def test_upload_validation_records_lowercase_sha256() -> None:
    data = build_pdf(["Checksum manual"])

    uploaded = validate_upload(
        filename="manual.pdf",
        declared_content_type="application/pdf",
        data=data,
        max_bytes=1024 * 1024,
        allowed_content_types=["application/pdf"],
    )

    assert uploaded.checksum_sha256 == hashlib.sha256(data).hexdigest()
    assert is_valid_sha256(uploaded.checksum_sha256)
    assert uploaded.checksum_sha256 == uploaded.checksum_sha256.lower()
