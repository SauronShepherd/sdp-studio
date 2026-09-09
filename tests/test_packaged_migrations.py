from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "migrations"
PACKAGED = ROOT / "python" / "sdpstudio_server" / "migrations"
MIGRATION_FILES = (
    "env.py",
    "script.py.mako",
    "versions/0001_initial.py",
    "versions/0002_spec_entities.py",
    "versions/0003_contract_fields.py",
    "versions/0004_project_soft_delete.py",
)


def test_packaged_migration_chain_matches_canonical_sources() -> None:
    for relative in MIGRATION_FILES:
        canonical = (CANONICAL / relative).read_bytes()
        packaged = (PACKAGED / relative).read_bytes()
        assert packaged == canonical
        assert hashlib.sha256(packaged).digest() == hashlib.sha256(canonical).digest()


def test_wheel_package_data_includes_migration_tree() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"migrations/*"' in pyproject
    assert '"migrations/versions/*"' in pyproject
