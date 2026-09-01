import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sdpstudio_core.models import RuntimeCapabilities
from sdpstudio_runners import profiles
from sdpstudio_server.app import create_app
from sdpstudio_server.runtime_profile_service import validate_runtime_profile
from sdpstudio_server.storage import DataStore


def test_runtime_profile_api_and_secret_guard(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    profiles_list = client.get("/api/runtime-profiles")
    assert profiles_list.status_code == 200
    assert profiles_list.json()[0]["adapter"] == "local"

    created = client.post(
        "/api/runtime-profiles",
        json={
            "name": "Remote dev",
            "adapter": "spark-connect",
            "config": {"remote_env": "SPARK_REMOTE"},
        },
    )
    assert created.status_code == 200
    profile_id = created.json()["id"]
    fetched = client.get(f"/api/runtime-profiles/{profile_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Remote dev"
    probed = client.get(f"/api/runtime-profiles/{profile_id}/probe")
    assert probed.status_code == 200
    assert probed.json()["adapter"] == "spark-connect"

    updated = client.patch(
        f"/api/runtime-profiles/{profile_id}",
        json={"name": "Remote staging", "config": {"remote_env": "SPARK_REMOTE_STAGING"}},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Remote staging"
    assert updated.json()["config"]["remote_env"] == "SPARK_REMOTE_STAGING"

    tested = client.post(f"/api/runtime-profiles/{profile_id}/test")
    assert tested.status_code == 200
    assert tested.json()["adapter"] == "spark-connect"

    unsafe = client.post(
        "/api/runtime-profiles",
        json={
            "name": "Unsafe",
            "adapter": "spark-connect",
            "config": {"remote": "sc://host/;token=plain-text-secret"},
        },
    )
    assert unsafe.status_code == 400


def test_external_runtime_profiles_require_administrator_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "runtime-profile-test-signing-key")
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "admin-password-123")
    client = TestClient(create_app(tmp_path))
    admin = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin-password-123"}
    )
    assert admin.status_code == 200
    csrf = client.cookies.get("sdpstudio_csrf")
    created_user = client.post(
        "/api/auth/users",
        json={"username": "editor", "password": "editor-password-123", "role": "editor"},
        headers={"X-CSRF-Token": csrf or ""},
    )
    assert created_user.status_code == 200
    client.post("/api/auth/logout")
    logged_in = client.post(
        "/api/auth/login", json={"username": "editor", "password": "editor-password-123"}
    )
    assert logged_in.status_code == 200
    response = client.post(
        "/api/runtime-profiles",
        json={
            "name": "cluster",
            "adapter": "kubernetes",
            "config": {"namespace": "data", "image": "spark:4.2"},
        },
    )
    assert response.status_code == 403


def test_kubernetes_command_builder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(profiles, "_upload_s3_artifact", lambda *args: None)
    project = tmp_path / "project"
    project.mkdir()
    (project / "spark-pipeline.yaml").write_text(
        "name: test\nlibraries:\n  - glob:\n      include: transformations/**\nstorage: file:///.sdpstudio/runtime/storage\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(profiles, "_spark_pipelines", lambda: "/opt/spark/bin/spark-pipelines")
    profile = {
        "adapter": "kubernetes",
        "config": {
            "master": "k8s://https://cluster.example:6443",
            "image": "registry.example/spark:4.2.0",
            "storage_uri": "s3a://bucket/sdpstudio/test",
            "namespace": "data",
            "service_account": "spark",
            "executor_instances": 3,
        },
    }
    command, safe, temp_spec = profiles.build_run_command(
        profile, project=project, run_id="01KTEST", mode="full-refresh-all", selected=[]
    )
    assert command == safe
    assert "--master" in command and "k8s://https://cluster.example:6443" in command
    assert "--deploy-mode" in command and "cluster" in command
    assert "spark.kubernetes.container.image=registry.example/spark:4.2.0" in command
    assert "spark.kubernetes.driver.pod.name=sdpstudio-01ktest-driver" in command
    assert "spark.kubernetes.namespace=data" in command
    assert "spark.kubernetes.authenticate.driver.serviceAccountName=spark" in command
    assert "spark.executor.instances=3" in command
    assert "--full-refresh-all" in command
    assert temp_spec is not None
    assert "storage: s3a://bucket/sdpstudio/test" in temp_spec.read_text(encoding="utf-8")
    assert temp_spec.parent == project / ".sdpstudio" / "runtime" / "run-artifacts" / "01KTEST"
    assert not list(project.glob(".sdpstudio-runtime-*.yaml"))
    manifest = temp_spec.parent / "staged-artifact-manifest.json"
    assert manifest.exists()
    assert "sha256" in manifest.read_text(encoding="utf-8")
    assert (temp_spec.parent / "staged" / "spark-pipeline.yaml").exists()
    staged_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    for item in staged_manifest["files"]:
        staged_file = project / item["staged_path"]
        assert hashlib.sha256(staged_file.read_bytes()).hexdigest() == item["sha256"]


def test_s3_artifact_upload_is_verified_without_shell(tmp_path: Path, monkeypatch):
    source = tmp_path / "generated.py"
    source.write_text("print('safe')\n", encoding="utf-8")
    remote: dict[str, bytes] = {}
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        if arguments[1:3] == ["s3", "cp"]:
            origin, target = arguments[3], arguments[4]
            if str(origin).startswith("s3://"):
                Path(target).write_bytes(remote[origin])
            else:
                remote[target] = Path(origin).read_bytes()
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(profiles.shutil, "which", lambda name: "aws" if name == "aws" else None)
    monkeypatch.setattr(profiles.subprocess, "run", fake_run)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    profiles._upload_s3_artifact(source, "s3://bucket/generated.py", digest)
    assert len(calls) == 2
    assert all(call[1]["check"] is True for call in calls)


def test_command_builder_rejects_flags_missing_from_authoritative_cli_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "spark-pipeline.yaml").write_text("name: test\n", encoding="utf-8")
    monkeypatch.setattr(profiles, "_spark_pipelines", lambda: "spark-pipelines")
    monkeypatch.setattr(
        profiles.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "Result", (), {"returncode": 0, "stdout": "--spec --conf\n", "stderr": ""}
        )(),
    )
    with pytest.raises(RuntimeError, match="does not support --full-refresh-all"):
        profiles.build_run_command(
            {"adapter": "local", "config": {}},
            project=project,
            run_id="01KTEST",
            mode="full-refresh-all",
            selected=[],
        )


def test_local_command_configures_run_scoped_event_logging(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(profiles, "_spark_pipelines", lambda: "spark-pipelines")
    project = tmp_path / "project"
    project.mkdir()
    (project / "spark-pipeline.yaml").write_text("name: demo\n", encoding="utf-8")

    command, safe, temp_spec = profiles.build_run_command(
        {"adapter": "local", "config": {}},
        project=project,
        run_id="01KTEST-EVENTS",
        mode="incremental",
        selected=[],
    )

    assert temp_spec is None
    assert command == safe
    assert "spark.eventLog.enabled=true" in command
    event_arg = next(value for value in command if value.startswith("spark.eventLog.dir="))
    assert event_arg.endswith("/.sdpstudio/runtime/event-logs/01KTEST-EVENTS")
    assert (project / ".sdpstudio" / "runtime" / "event-logs" / "01KTEST-EVENTS").is_dir()


def test_kubernetes_command_builder_supports_resources_labels_and_redacts_secret_conf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(profiles, "_upload_s3_artifact", lambda *args: None)
    monkeypatch.setattr(profiles, "_spark_pipelines", lambda: "spark-pipelines")
    project = tmp_path / "project"
    project.mkdir()
    (project / "spark-pipeline.yaml").write_text("name: demo\n", encoding="utf-8")
    profile = {
        "adapter": "kubernetes",
        "config": {
            "master": "k8s://https://cluster",
            "image": "registry.example/spark:4.2.0",
            "storage_uri": "s3a://bucket/pipeline",
            "driver_cores": 2,
            "driver_memory": "2g",
            "executor_cores": 4,
            "executor_memory": "8g",
            "image_pull_secrets": ["registry-secret"],
            "labels": {"team": "data"},
            "annotations": {"team.example/owner": "sdpstudio"},
            "spark_conf": {"spark.executor.memoryOverhead": "1g", "spark.auth.token": "hidden"},
        },
    }
    command, safe, temp_spec = profiles.build_run_command(
        profile, project=project, run_id="01KTEST", mode="incremental", selected=[]
    )
    assert temp_spec is not None
    assert "spark.driver.cores=2" in command
    assert "spark.kubernetes.driver.label.team=data" in command
    assert "spark.kubernetes.driver.annotation.team.example/owner=sdpstudio" in command
    assert "spark.auth.token=hidden" in command
    assert "spark.auth.token=***REDACTED***" in safe
    assert "hidden" not in " ".join(safe)
    temp_spec.unlink()


def test_kubernetes_command_builder_rejects_non_spark_custom_conf(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(profiles, "_upload_s3_artifact", lambda *args: None)
    monkeypatch.setattr(profiles, "_spark_pipelines", lambda: "spark-pipelines")
    project = tmp_path / "project"
    project.mkdir()
    (project / "spark-pipeline.yaml").write_text("name: demo\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"spark\.\* keys"):
        profiles.build_run_command(
            {
                "adapter": "kubernetes",
                "config": {
                    "master": "k8s://x",
                    "image": "spark",
                    "storage_uri": "s3://x",
                    "spark_conf": {"--evil": "x"},
                },
            },
            project=project,
            run_id="01KTEST",
            mode="incremental",
            selected=[],
        )


def test_kubernetes_probe_requires_kubectl(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(profiles, "_spark_pipelines", lambda: "spark-pipelines")
    monkeypatch.setattr(profiles, "probe_local", lambda: RuntimeCapabilities(spark_version="4.2"))
    monkeypatch.setattr(profiles.shutil, "which", lambda name: "java" if name == "java" else None)
    result = profiles.probe_profile(
        {
            "adapter": "kubernetes",
            "config": {"master": "k8s://cluster", "image": "spark", "storage_uri": "s3://bucket"},
        }
    )
    assert result.available is False


def test_kubernetes_live_probe_checks_namespace_without_shell(monkeypatch: pytest.MonkeyPatch):
    calls = []

    class Result:
        returncode = 0
        stdout = "namespace/data\n"
        stderr = ""

    monkeypatch.setattr(profiles.shutil, "which", lambda name: "kubectl")
    monkeypatch.setattr(
        profiles.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)) or Result(),
    )
    result = profiles.probe_kubernetes_live(
        {"adapter": "kubernetes", "config": {"namespace": "data"}}
    )
    assert result["ok"] is True
    assert calls[0][0][-7:] == ["-n", "data", "get", "namespace", "data", "-o", "name"]
    assert calls[0][1]["shell"] is False


def test_kubernetes_profile_enforces_namespace_and_pod_allowlists():
    from sdpstudio_server.runtime_profile_service import validate_runtime_profile

    config = {
        "master": "k8s://https://cluster",
        "image": "registry.example/spark:4.2.0",
        "storage_uri": "s3a://bucket/path",
        "namespace": "data",
        "allowed_namespaces": ["data"],
        "pod_name_prefix": "sdpstudio-",
        "allowed_pod_prefixes": ["sdpstudio-"],
    }
    validate_runtime_profile("kubernetes", config)
    with pytest.raises(ValueError, match="allowlist"):
        validate_runtime_profile("kubernetes", {**config, "namespace": "other"})


def test_kubernetes_profile_has_typed_resource_validation():
    from sdpstudio_server.runtime_profile_service import validate_runtime_profile

    with pytest.raises(ValueError, match="greater than or equal to 1"):
        validate_runtime_profile("kubernetes", {"driver_cores": 0})


def test_kubernetes_profile_enforces_admin_service_account_and_path_policies():
    config = {
        "namespace": "data",
        "service_account": "spark-driver",
        "allowed_service_accounts": ["spark-driver"],
        "pod_template_path": "k8s/driver.yaml",
        "secret_references": ["secret://registry"],
        "allowed_secret_references": ["secret://registry"],
    }
    validate_runtime_profile("kubernetes", config)
    with pytest.raises(ValueError, match="service account"):
        validate_runtime_profile("kubernetes", {**config, "service_account": "other"})
    with pytest.raises(ValueError, match="relative"):
        validate_runtime_profile("kubernetes", {**config, "pod_template_path": "../driver.yaml"})
    with pytest.raises(ValueError, match="secret reference"):
        validate_runtime_profile("kubernetes", {**config, "secret_references": ["secret://other"]})


def test_remote_command_redacts_token_and_store_rejects_literal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "spark-pipeline.yaml").write_text(
        "name: test\nlibraries: []\nstorage: file:///tmp\n", encoding="utf-8"
    )
    monkeypatch.setattr(profiles, "_spark_pipelines", lambda: "/bin/spark-pipelines")
    monkeypatch.setenv("SPARK_REMOTE_PRIVATE", "sc://spark.example:15002/;token=very-secret")
    profile = {"adapter": "spark-connect", "config": {"remote_env": "SPARK_REMOTE_PRIVATE"}}
    command, safe, _ = profiles.build_run_command(
        profile, project=project, run_id="01KTEST2", mode="incremental", selected=[]
    )
    assert "very-secret" in " ".join(command)
    assert "very-secret" not in " ".join(safe)

    store = DataStore(tmp_path / "data")
    with pytest.raises(ValueError):
        store.create_runtime_profile("bad", "spark-connect", {"remote": "sc://x/;token=literal"})


def test_managed_databricks_profile_requires_explicit_workspace():
    from sdpstudio_server.runtime_profile_service import validate_runtime_profile

    validate_runtime_profile("databricks", {"workspace_url": "https://example.databricks.com"})
    with pytest.raises(ValueError, match="workspace_url"):
        validate_runtime_profile("databricks", {"workspace_url": "example.databricks.com"})
