from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from .storage import atomic_write


class FileConflictError(RuntimeError):
    """Raised when an editor write is based on a stale content hash."""


class UnsafePathError(ValueError):
    """Raised when a path escapes the configured project root."""


@dataclass(frozen=True)
class FileInfo:
    path: str
    kind: str
    size: int
    etag: str | None = None


class ProjectFileSystem:
    """Safe, atomic, project-relative text file access for editor APIs."""

    def __init__(self, max_file_size: int = 2 * 1024 * 1024):
        self.max_file_size = max_file_size
        self._locks: dict[Path, RLock] = {}
        self._locks_guard = RLock()

    def _lock(self, root: Path) -> RLock:
        root = root.resolve()
        with self._locks_guard:
            return self._locks.setdefault(root, RLock())

    @staticmethod
    def resolve(root: Path, relative: str) -> Path:
        if not relative or "\x00" in relative:
            raise UnsafePathError("A non-empty relative path is required")
        candidate = (root / relative).resolve()
        root = root.resolve()
        if candidate != root and root not in candidate.parents:
            raise UnsafePathError("Path escapes the project root")
        return candidate

    @staticmethod
    def _etag(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def tree(self, root: Path) -> list[FileInfo]:
        root = root.resolve()
        if not root.is_dir():
            raise FileNotFoundError(root)
        entries: list[FileInfo] = []
        for path in sorted(root.rglob("*")):
            if any(part in {".git", "__pycache__", "node_modules"} for part in path.parts):
                continue
            relative = path.relative_to(root).as_posix()
            if path.is_dir():
                entries.append(FileInfo(relative, "directory", 0))
            elif path.is_file():
                entries.append(FileInfo(relative, "file", path.stat().st_size, self._etag(path)))
        return entries

    def read_text(self, root: Path, relative: str) -> tuple[str, FileInfo]:
        path = self.resolve(root, relative)
        if not path.is_file():
            raise FileNotFoundError(relative)
        if path.stat().st_size > self.max_file_size:
            raise ValueError(f"File exceeds the {self.max_file_size}-byte editor limit")
        raw = path.read_bytes()
        if b"\x00" in raw:
            raise ValueError("Binary files are metadata-only and cannot be edited")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("File is not valid UTF-8 text") from exc
        return text, FileInfo(
            path.relative_to(root.resolve()).as_posix(),
            "file",
            len(raw),
            hashlib.sha256(raw).hexdigest(),
        )

    def write_text(
        self, root: Path, relative: str, text: str, expected_etag: str | None = None
    ) -> FileInfo:
        if "\x00" in text:
            raise ValueError("NUL bytes are not permitted in text files")
        encoded = text.encode("utf-8")
        if len(encoded) > self.max_file_size:
            raise ValueError(f"File exceeds the {self.max_file_size}-byte editor limit")
        root = root.resolve()
        path = self.resolve(root, relative)
        with self._lock(root):
            current = self._etag(path) if path.is_file() else None
            if expected_etag is not None and current != expected_etag:
                raise FileConflictError("File changed since it was loaded")
            atomic_write(path, text)
            return FileInfo(
                relative.replace(os.sep, "/"),
                "file",
                len(encoded),
                hashlib.sha256(encoded).hexdigest(),
            )

    @staticmethod
    def _mutable(root: Path, relative: str) -> Path:
        path = ProjectFileSystem.resolve(root, relative)
        if ".git" in path.relative_to(root.resolve()).parts:
            raise UnsafePathError("Git internals are not editable through the explorer")
        return path

    def create_directory(self, root: Path, relative: str) -> FileInfo:
        root = root.resolve()
        path = self._mutable(root, relative)
        if path.exists():
            raise FileExistsError(relative)
        path.mkdir(parents=False)
        return FileInfo(path.relative_to(root).as_posix(), "directory", 0)

    def delete(self, root: Path, relative: str, expected_etag: str | None = None) -> None:
        root = root.resolve()
        path = self._mutable(root, relative)
        if path == root or not path.exists():
            raise FileNotFoundError(relative)
        if path.is_file():
            if expected_etag is not None and self._etag(path) != expected_etag:
                raise FileConflictError("File changed since it was loaded")
            path.unlink()
        else:
            path.rmdir()

    def rename(self, root: Path, old: str, new: str, expected_etag: str | None = None) -> FileInfo:
        root = root.resolve()
        source = self._mutable(root, old)
        target = self._mutable(root, new)
        if not source.exists() or target.exists():
            raise FileNotFoundError(old) if not source.exists() else FileExistsError(new)
        if source.is_file() and expected_etag is not None and self._etag(source) != expected_etag:
            raise FileConflictError("File changed since it was loaded")
        target.parent.mkdir(parents=False, exist_ok=True)
        source.rename(target)
        return FileInfo(
            target.relative_to(root).as_posix(),
            "directory" if target.is_dir() else "file",
            target.stat().st_size,
            self._etag(target) if target.is_file() else None,
        )
