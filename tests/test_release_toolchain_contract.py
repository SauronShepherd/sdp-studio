from __future__ import annotations

import json
from pathlib import Path


def test_workspace_pins_pnpm_release() -> None:
    package = json.loads(Path("package.json").read_text(encoding="utf-8"))

    assert package["packageManager"] == "pnpm@9.15.9"


def test_release_container_uses_pinned_pnpm_without_legacy_prod_false() -> None:
    dockerfile = Path("deploy/docker/Dockerfile").read_text(encoding="utf-8")

    assert "corepack prepare pnpm@9.15.9 --activate" in dockerfile
    assert "--prod=false" not in dockerfile


def test_no_isolation_package_job_installs_declared_build_backend() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "python -m pip install build setuptools wheel" in workflow
    assert "python -m build --wheel --sdist --no-isolation" in workflow


def test_packaged_migration_chain_matches_canonical_sources() -> None:
    canonical_root = Path("migrations")
    packaged_root = Path("python/sdpstudio_server/migrations")
    for relative in (
        "env.py",
        "script.py.mako",
        "versions/0001_initial.py",
        "versions/0002_spec_entities.py",
        "versions/0003_contract_fields.py",
        "versions/0004_project_soft_delete.py",
    ):
        assert (packaged_root / relative).read_bytes() == (canonical_root / relative).read_bytes()


def test_wheel_package_data_includes_migration_tree() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"migrations/*"' in pyproject
    assert '"migrations/versions/*"' in pyproject
