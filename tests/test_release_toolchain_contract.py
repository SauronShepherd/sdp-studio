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
