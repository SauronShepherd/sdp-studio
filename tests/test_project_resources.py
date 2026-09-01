import sys
from pathlib import Path

import pytest
from sdpstudio_server.project_resources import ProjectResourceService


def test_project_resource_service_preserves_safe_file_and_catalog_contract(tmp_path: Path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "orders.csv").write_text("id,status\n1,ok\n", encoding="utf-8")
    service = ProjectResourceService()
    info = service.write_text(tmp_path, "notes.txt", "hello", None)
    content, loaded = service.read_text(tmp_path, "notes.txt")
    assert content == "hello"
    assert loaded.etag == info.etag
    assert service.catalog(tmp_path)["tables"][0]["name"] == "orders"


def test_project_resource_service_resolves_only_workspace_paths(tmp_path):
    service = ProjectResourceService(workspace_root=tmp_path / "projects")
    (tmp_path / "projects" / "demo").mkdir(parents=True)
    assert (
        service.resolve_project_path({"path": str(tmp_path / "projects" / "demo")}).name == "demo"
    )
    with pytest.raises(ValueError, match="escaped workspace"):
        service.resolve_project_path({"path": str(tmp_path / "outside")})
    assert service.workspace_available()


def test_runtime_catalog_is_cached_and_separate_from_filesystem_discovery():
    service = ProjectResourceService()
    profile = {
        "id": "runtime-1",
        "adapter": "spark-connect",
        "config": {
            "catalog": {"catalog": "main", "namespace": "sales", "tables": [{"name": "orders"}]}
        },
    }
    first = service.runtime_catalog(profile)
    profile["config"]["catalog"]["tables"].append({"name": "customers"})
    assert service.runtime_catalog(profile) == first
    with pytest.raises(RuntimeError, match="SDPS-CATALOG-001"):
        service.runtime_catalog({"id": "unavailable", "adapter": "local", "config": {}})


def test_runtime_catalog_can_query_an_explicit_runtime_command(tmp_path: Path):
    service = ProjectResourceService(workspace_root=tmp_path)
    profile = {
        "id": "runtime-command",
        "adapter": "spark-connect",
        "config": {
            "catalog_command": [
                sys.executable,
                "-c",
                'print(\'{"catalog":"main","namespace":"sales","tables":[{"name":"orders"}]}\')',
            ]
        },
    }
    result = service.runtime_catalog(profile, tmp_path)
    assert result["source"] == "runtime-command"
    assert result["tables"][0]["name"] == "orders"


def test_runtime_catalog_rejects_invalid_command_output(tmp_path: Path):
    service = ProjectResourceService(workspace_root=tmp_path)
    profile = {
        "id": "bad-command",
        "config": {"catalog_command": [sys.executable, "-c", "print('nope')"]},
    }
    with pytest.raises(RuntimeError, match="SDPS-CATALOG-004"):
        service.runtime_catalog(profile)
