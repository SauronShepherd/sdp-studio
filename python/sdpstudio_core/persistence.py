from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

CURRENT_SCHEMA_VERSION = 1


def _migrate_v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(data)
    migrated.setdefault("schemaVersion", 1)
    return migrated


SCHEMA_MIGRATIONS: dict[int, Any] = {0: _migrate_v0_to_v1}


def migrate_document(
    data: dict[str, Any], from_version: int, to_version: int = CURRENT_SCHEMA_VERSION
) -> dict[str, Any]:
    if from_version > to_version:
        raise ValueError("document schema is newer than this SDP Studio version")
    migrated = dict(data)
    version = from_version
    while version < to_version:
        migration = SCHEMA_MIGRATIONS.get(version)
        if migration is None:
            raise ValueError(f"no migration registered from document schema v{version}")
        migrated = migration(migrated)
        version += 1
    return migrated


def migrate(
    document: dict[str, Any], from_version: int, to_version: int = CURRENT_SCHEMA_VERSION
) -> dict[str, Any]:
    """Migrate a persisted document without mutating the caller's mapping."""
    return migrate_document(document, from_version, to_version)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("document root must be a mapping")
    version = int(raw.get("schemaVersion", 0))
    return migrate_document(raw, version)


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def upgrade_yaml(path: Path, to_version: int = CURRENT_SCHEMA_VERSION) -> Path | None:
    """Upgrade a persisted YAML document, preserving a sibling backup first.

    Returns the backup path when a migration was applied, otherwise ``None``.
    The operation is local and deterministic; callers can restore the backup if
    a later validation step fails.
    """
    raw = load_yaml_raw(path)
    from_version = int(raw.get("schemaVersion", 0))
    if from_version == to_version:
        return None
    migrated = migrate_document(raw, from_version, to_version)
    backup = path.with_name(f"{path.name}.v{from_version}.bak")
    if backup.exists():
        backup = path.with_name(f"{path.name}.v{from_version}.bak.1")
    shutil.copy2(path, backup)
    save_yaml(path, migrated)
    return backup


def load_yaml_raw(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("document root must be a mapping")
    return raw
