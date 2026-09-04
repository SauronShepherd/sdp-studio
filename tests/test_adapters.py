import inspect
import sys
from pathlib import Path

import pytest
from sdpstudio_runners.adapters import (
    DurableLocalRuntimeAdapter,
    KubernetesLifecycle,
    LocalRuntimeAdapter,
    RuntimeAdapter,
    adapter_for,
)


def test_async_runtime_contract_names_all_required_operations():
    for name in (
        "probe",
        "validate",
        "preview",
        "submit",
        "cancel",
        "status",
        "stream_events",
        "collect_artifacts",
    ):
        assert inspect.iscoroutinefunction(
            getattr(RuntimeAdapter, name)
        ) or inspect.isasyncgenfunction(getattr(RuntimeAdapter, name))
        assert inspect.iscoroutinefunction(
            getattr(DurableLocalRuntimeAdapter, name)
        ) or inspect.isasyncgenfunction(getattr(DurableLocalRuntimeAdapter, name))


def test_durable_adapter_resolves_registered_project(tmp_path: Path):
    class Store:
        def list_projects(self):
            return [{"id": "project-1", "path": str(tmp_path)}]

    class Runtime:
        store = Store()

    adapter = DurableLocalRuntimeAdapter(Runtime())
    assert adapter._project_id(tmp_path) == "project-1"
    with pytest.raises(ValueError, match="not registered"):
        adapter._project_id(tmp_path / "missing")


def test_runtime_adapter_contract_delegates_probe(monkeypatch: pytest.MonkeyPatch):
    from sdpstudio_runners import adapters

    monkeypatch.setattr(
        adapters,
        "probe_profile",
        lambda profile: type("Capabilities", (), {"available": True})(),
    )
    adapter = adapter_for({"adapter": "local"})
    report = adapter.probe({"adapter": "local"})
    assert report.adapter == "local"
    assert report.available is True


def test_adapter_factory_rejects_unknown_profiles():
    with pytest.raises(ValueError, match="Unsupported"):
        adapter_for({"adapter": "unknown"})


def test_adapter_factory_registers_managed_databricks():
    adapter = adapter_for(
        {"adapter": "databricks", "config": {"workspace_url": "https://example.databricks.com"}}
    )
    assert adapter.name == "databricks"


def test_adapter_command_rejects_mismatched_profile():
    with pytest.raises(ValueError, match="not 'local'"):
        adapter_for({"adapter": "local"}).command(
            {"adapter": "spark-connect"},
            project=Path("."),
            run_id="run",
            mode="incremental",
            selected=[],
        )


def test_kubernetes_lifecycle_commands_are_deterministic_and_safe():
    lifecycle = KubernetesLifecycle("data", "spark-driver-123")
    status, safe_status = lifecycle.status_command()
    logs, safe_logs = lifecycle.logs_command(tail=50, follow=True)
    cancel, safe_cancel = lifecycle.cancel_command(grace_period=10)
    events, safe_events = lifecycle.events_command()
    executors, safe_executors = lifecycle.executor_pods_command()
    access, safe_access = lifecycle.access_check_command()
    assert (
        status
        == safe_status
        == ["kubectl", "-n", "data", "get", "pod", "spark-driver-123", "-o", "json"]
    )
    assert logs == safe_logs and "--follow" in logs
    assert cancel == safe_cancel and "--grace-period" in cancel
    assert events == safe_events and "involvedObject.name=spark-driver-123" in events
    assert executors == safe_executors and "spark-app-selector=spark-spark-driver-123" in executors
    assert access == safe_access == ["kubectl", "-n", "data", "auth", "can-i", "get", "pods"]
    assert [name for name, _, _ in lifecycle.access_check_commands()] == [
        "get",
        "list",
        "watch",
        "create",
        "delete",
        "logs",
    ]
    with pytest.raises(ValueError):
        KubernetesLifecycle("data;rm", "driver")
    with pytest.raises(ValueError):
        lifecycle.logs_command(tail=0)


@pytest.mark.asyncio
async def test_local_async_adapter_exposes_all_runtime_operations(tmp_path: Path, monkeypatch):
    adapter = LocalRuntimeAdapter()
    command = [sys.executable, "-c", "pass"]
    monkeypatch.setattr(
        "sdpstudio_runners.adapters.build_run_command",
        lambda *args, **kwargs: (command, command, None),
    )
    profile = {"adapter": "local", "config": {}}
    validation = await adapter.validate(profile, tmp_path)
    assert validation.valid
    preview = await adapter.preview(profile, tmp_path, "node-1", 10)
    assert preview.metrics == {"node_id": "node-1", "limit": 10, "isolated": True}
    handle = await adapter.submit(profile, tmp_path, "run-1", "incremental", [])
    events = [event async for event in adapter.stream_events(handle)]
    assert events == []
    assert (await adapter.status(handle)).state == "succeeded"
    assert await adapter.collect_artifacts(handle) == []


@pytest.mark.asyncio
async def test_local_async_adapter_closes_stream_when_process_spawn_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    adapter = LocalRuntimeAdapter()
    command = ["definitely-not-an-sdpstudio-runtime-command"]
    monkeypatch.setattr(
        "sdpstudio_runners.adapters.build_run_command",
        lambda *args, **kwargs: (command, command, None),
    )
    profile = {"adapter": "local", "config": {}}
    handle = await adapter.submit(profile, tmp_path, "run-failed", "incremental", [])

    assert [event async for event in adapter.stream_events(handle)] == []
    status = await adapter.status(handle)
    assert status.state == "failed"
    assert status.message


@pytest.mark.asyncio
async def test_durable_stream_events_ends_on_validation_failure():
    class Store:
        def run_events(self, run_id, sequence):
            return []

        def get_run(self, run_id):
            return {"status": "validation_failed", "error": "invalid graph"}

    class Runtime:
        store = Store()

    adapter = DurableLocalRuntimeAdapter(Runtime())
    events = [
        event async for event in adapter.stream_events(type("Handle", (), {"run_id": "r1"})())
    ]
    assert events == []
