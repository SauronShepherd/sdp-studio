from __future__ import annotations

import json
from pathlib import Path

from sdpstudio_server.migration_paths import configure_installed_migrations_default


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


def test_wheel_data_files_include_canonical_migration_tree() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"share/sdpstudio" = ["alembic.ini"]' in pyproject
    assert '"share/sdpstudio/migrations"' in pyproject
    assert '["migrations/env.py", "migrations/script.py.mako"]' in pyproject
    assert '"share/sdpstudio/migrations/versions"' in pyproject
    assert '["migrations/versions/*.py"]' in pyproject


def test_installed_migration_fallback_uses_python_data_scheme(tmp_path, monkeypatch) -> None:
    migration_root = tmp_path / "share" / "sdpstudio" / "migrations"
    (migration_root / "versions").mkdir(parents=True)
    (migration_root / "env.py").write_text("# migration env\n", encoding="utf-8")
    monkeypatch.delenv("SDPSTUDIO_MIGRATIONS_PATH", raising=False)

    resolved = configure_installed_migrations_default(data_root=str(tmp_path))

    assert resolved == migration_root
    assert Path(str(__import__("os").environ["SDPSTUDIO_MIGRATIONS_PATH"])) == migration_root


def test_explicit_migration_override_wins(tmp_path, monkeypatch) -> None:
    explicit = tmp_path / "explicit"
    monkeypatch.setenv("SDPSTUDIO_MIGRATIONS_PATH", str(explicit))

    assert configure_installed_migrations_default(data_root=str(tmp_path / "other")) == explicit
