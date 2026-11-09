from __future__ import annotations

import os
import tempfile
import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from app.core.config import Settings


@dataclass(frozen=True)
class StorageObjectInfo:
    key: str
    size: int
    modified_at: float


class StorageError(Exception):
    """Base class for storage failures."""


class InvalidStorageKeyError(StorageError):
    """Raised when a storage key is unsafe or malformed."""


class StorageObjectNotFoundError(StorageError):
    """Raised when a requested storage object does not exist."""


class StorageObjectExistsError(StorageError):
    """Raised when a write would overwrite an existing object."""


class StorageFileTooLargeError(StorageError):
    """Raised when an upload exceeds the configured storage limit."""


class DocumentStorage(ABC):
    @abstractmethod
    def save(
        self,
        key: str,
        data: bytes,
        *,
        overwrite: bool = False,
    ) -> None:
        """Persist bytes under an app-generated storage key."""

    @abstractmethod
    def open(self, key: str) -> BinaryIO:
        """Open a stored object for binary reading."""

    @abstractmethod
    def read(self, key: str) -> bytes:
        """Return the full contents of a stored object."""

    def local_path(self, key: str) -> Path:
        """Return a verified filesystem path for locally backed storage.

        Drivers that cannot expose a usable local path raise ``StorageError``;
        callers must not assume every storage backend is filesystem-backed.
        """

        raise StorageError("Storage backend does not expose local file paths")

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete an object. Return False when it was already absent."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return whether an object exists."""

    @abstractmethod
    def generate_key(self, original_filename: str | None = None) -> str:
        """Generate an unpredictable storage key."""

    @abstractmethod
    def iter_keys(self) -> Iterator[str]:
        """Yield stored object keys for reconciliation tooling."""

    @abstractmethod
    def iter_temp_keys(self) -> Iterator[str]:
        """Yield in-progress/temporary upload keys for reconciliation."""

    @abstractmethod
    def stat_key(self, key: str) -> StorageObjectInfo:
        """Return size and modification time for an existing object."""


class LocalFileStorage(DocumentStorage):
    """Private local-filesystem storage with traversal-safe key resolution."""

    def __init__(self, root: Path, *, max_bytes: int | None = None) -> None:
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._max_bytes = max_bytes

    @property
    def root(self) -> Path:
        return self._root

    def generate_key(self, original_filename: str | None = None) -> str:
        token = uuid.uuid4().hex
        return f"{token[:2]}/{token}.pdf"

    def save(
        self,
        key: str,
        data: bytes,
        *,
        overwrite: bool = False,
    ) -> None:
        if self._max_bytes is not None and len(data) > self._max_bytes:
            raise StorageFileTooLargeError("Stored object exceeds size limit")

        target = self._resolve_key(key)
        if not overwrite and target.exists():
            raise StorageObjectExistsError("Storage object already exists")

        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self._is_within(parent.resolve(), self._root):
            raise InvalidStorageKeyError("Storage path escapes the root")

        temp_name: str | None = None
        try:
            descriptor, temp_name = tempfile.mkstemp(
                prefix=".upload-",
                dir=parent,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())

            if not overwrite and target.exists():
                raise StorageObjectExistsError("Storage object already exists")

            os.replace(temp_name, target)
            temp_name = None
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass

    def open(self, key: str) -> BinaryIO:
        path = self._resolve_existing_key(key)
        return path.open("rb")

    def read(self, key: str) -> bytes:
        with self.open(key) as handle:
            return handle.read()

    def local_path(self, key: str) -> Path:
        return self._resolve_existing_key(key)

    def delete(self, key: str) -> bool:
        path = self._resolve_key(key)
        if not path.exists():
            return False
        if path.is_symlink() or not path.is_file():
            raise InvalidStorageKeyError("Storage key is not a regular file")
        path.unlink()
        return True

    def exists(self, key: str) -> bool:
        path = self._resolve_key(key)
        if path.is_symlink():
            raise InvalidStorageKeyError("Storage key is a symbolic link")
        return path.is_file()

    def iter_keys(self) -> Iterator[str]:
        yield from self._iter_files(include_temp=False)

    def iter_temp_keys(self) -> Iterator[str]:
        yield from self._iter_files(include_temp=True)

    def stat_key(self, key: str) -> StorageObjectInfo:
        path = self._resolve_existing_key(key)
        details = path.stat()
        return StorageObjectInfo(
            key=key,
            size=details.st_size,
            modified_at=details.st_mtime,
        )

    def _iter_files(self, *, include_temp: bool) -> Iterator[str]:
        for directory, subdirectories, filenames in os.walk(
            self._root,
            followlinks=False,
        ):
            subdirectories[:] = [
                name
                for name in subdirectories
                if not (Path(directory) / name).is_symlink()
            ]
            for filename in filenames:
                path = Path(directory) / filename
                if path.is_symlink() or not path.is_file():
                    continue
                is_temp = filename.startswith(".upload-")
                if is_temp != include_temp:
                    continue
                yield path.relative_to(self._root).as_posix()

    def _resolve_existing_key(self, key: str) -> Path:
        path = self._resolve_key(key)
        if not path.exists() or not path.is_file():
            raise StorageObjectNotFoundError("Storage object not found")
        resolved = path.resolve(strict=True)
        if not self._is_within(resolved, self._root):
            raise InvalidStorageKeyError("Storage path escapes the root")
        return resolved

    def _resolve_key(self, key: str) -> Path:
        if not isinstance(key, str) or not key.strip():
            raise InvalidStorageKeyError("Storage key is empty")

        normalized = key.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if pure.is_absolute():
            raise InvalidStorageKeyError("Storage key must be relative")

        parts = pure.parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise InvalidStorageKeyError("Storage key contains invalid parts")
        if ":" in parts[0]:
            raise InvalidStorageKeyError("Storage key must not contain a drive")

        lexical = self._root / Path(*parts)
        parent = lexical.parent.resolve()
        if not self._is_within(parent, self._root):
            raise InvalidStorageKeyError("Storage path escapes the root")

        if lexical.is_symlink():
            raise InvalidStorageKeyError("Storage key is a symbolic link")

        if lexical.exists():
            resolved = lexical.resolve(strict=True)
            if not self._is_within(resolved, self._root):
                raise InvalidStorageKeyError("Storage path escapes the root")
            return resolved

        return lexical

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            return os.path.commonpath([str(path), str(root)]) == str(root)
        except ValueError:
            return False


def build_document_storage(settings: Settings) -> DocumentStorage:
    return LocalFileStorage(
        settings.storage_root,
        max_bytes=settings.max_upload_size_bytes,
    )
