from __future__ import annotations

from pathlib import Path

import pytest

from app.services.documents import storage as storage_module
from app.services.documents.storage import (
    InvalidStorageKeyError,
    LocalFileStorage,
    StorageFileTooLargeError,
    StorageObjectExistsError,
    StorageObjectNotFoundError,
)


def _storage(tmp_path: Path, *, max_bytes: int | None = None) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "root", max_bytes=max_bytes)


def test_generated_keys_are_unpredictable_and_filename_independent(
    tmp_path: Path,
) -> None:
    storage = _storage(tmp_path)

    first = storage.generate_key("../../secret-manual.pdf")
    second = storage.generate_key("../../secret-manual.pdf")

    assert first != second
    assert first.endswith(".pdf")
    assert "secret" not in first
    assert ".." not in first


@pytest.mark.parametrize(
    "key",
    [
        "",
        "../outside.pdf",
        "a/../../outside.pdf",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "aa/..\\..\\outside.pdf",
    ],
)
def test_unsafe_keys_are_rejected(tmp_path: Path, key: str) -> None:
    storage = _storage(tmp_path)

    with pytest.raises(InvalidStorageKeyError):
        storage.save(key, b"%PDF-1.4")

    with pytest.raises(InvalidStorageKeyError):
        storage.read(key)

    with pytest.raises(InvalidStorageKeyError):
        storage.exists(key)

    with pytest.raises(InvalidStorageKeyError):
        storage.delete(key)

    with pytest.raises(InvalidStorageKeyError):
        storage.local_path(key)


def test_local_path_resolves_existing_object_inside_root(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    key = storage.generate_key()
    storage.save(key, b"%PDF-1.4")

    path = storage.local_path(key)

    assert path.is_file()
    assert path.resolve().is_relative_to(storage.root)


def test_local_path_rejects_missing_object(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    with pytest.raises(StorageObjectNotFoundError):
        storage.local_path("aa/missing.pdf")


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("private", encoding="utf-8")

    link = storage.root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symbolic links are not permitted on this platform")

    with pytest.raises(InvalidStorageKeyError):
        storage.read("escape/secret.txt")

    file_link = storage.root / "linked.pdf"
    try:
        file_link.symlink_to(outside / "secret.txt")
    except OSError:
        pytest.skip("Symbolic links are not permitted on this platform")

    with pytest.raises(InvalidStorageKeyError):
        storage.exists("linked.pdf")

    with pytest.raises(InvalidStorageKeyError):
        storage.local_path("linked.pdf")


def test_file_size_limit_is_enforced(tmp_path: Path) -> None:
    storage = _storage(tmp_path, max_bytes=4)

    with pytest.raises(StorageFileTooLargeError):
        storage.save("aa/too-large.pdf", b"12345")

    assert list(storage.iter_keys()) == []


def test_duplicate_write_requires_explicit_overwrite(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    key = storage.generate_key()

    storage.save(key, b"first")

    with pytest.raises(StorageObjectExistsError):
        storage.save(key, b"second")

    storage.save(key, b"second", overwrite=True)
    assert storage.read(key) == b"second"


def test_read_missing_object_raises(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    assert storage.exists("aa/missing.pdf") is False
    with pytest.raises(StorageObjectNotFoundError):
        storage.read("aa/missing.pdf")


def test_delete_is_idempotent(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    key = storage.generate_key()
    storage.save(key, b"content")

    assert storage.delete(key) is True
    assert storage.delete(key) is False
    assert storage.exists(key) is False


def test_partial_write_leaves_no_target_or_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    key = storage.generate_key()

    def fail_replace(source: object, destination: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(storage_module.os, "replace", fail_replace)

    with pytest.raises(OSError):
        storage.save(key, b"content")

    assert storage.exists(key) is False
    leftovers = [
        path
        for path in (storage.root / "aa").glob(".upload-*")
        if path.exists()
    ]
    assert leftovers == []
