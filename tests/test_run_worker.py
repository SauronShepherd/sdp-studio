import asyncio
from pathlib import Path

import pytest
from sdpstudio_core.models import RunRecord
from sdpstudio_runners.adapters import RunHandle, RunStatus, ValidationResult
from sdpstudio_server.run_worker import DurableRunWorker, execute_queued_local_run
from sdpstudio_server.storage import DataStore


def test_postgres_claim_path_uses_skip_locked():
    source = Path("python/sdpstudio_server/storage.py").read_text(encoding="utf-8")
    assert "FOR UPDATE SKIP LOCKED" in source


def test_durable_worker_claims_and_executes_once(tmp_path):
    store = DataStore(tmp_path)
    project = store.create_project("worker")
    record = RunRecord(project_id=project["id"], status="queued")
    store.create_run(record)
    seen = []
    worker = DurableRunWorker(store, "worker-a", lambda item: seen.append(item["id"]))
    assert worker.poll_once()["id"] == record.id
    assert seen == [record.id]
    assert worker.poll_once() is None


def test_durable_worker_releases_claim_on_executor_failure(tmp_path):
    store = DataStore(tmp_path)
    project = store.create_project("worker-failure")
    record = RunRecord(project_id=project["id"], status="queued")
    store.create_run(record)

    def fail(_item):
        raise RuntimeError("expected")

    with pytest.raises(RuntimeError, match="expected"):
        DurableRunWorker(store, "worker-a", fail).poll_once()
    assert store.get_run(record.id)["claim_token"] is None


def test_durable_worker_supports_async_execution_and_releases_successful_lease(tmp_path):
    store = DataStore(tmp_path)
    project = store.create_project("worker-async")
    record = RunRecord(project_id=project["id"], status="queued")
    store.create_run(record)
    seen: list[str] = []

    async def execute(item):
        await asyncio.sleep(0)
        seen.append(item["id"])

    completed = asyncio.run(
        DurableRunWorker(store, "worker-a", lambda _item: None).drain_async(
            executor=execute, limit=1
        )
    )
    assert [item["id"] for item in completed] == [record.id]
    assert seen == [record.id]
    assert store.get_run(record.id)["claim_token"] is None


def test_durable_worker_renews_long_running_lease(tmp_path):
    store = DataStore(tmp_path)
    project = store.create_project("worker-heartbeat")
    record = RunRecord(project_id=project["id"], status="queued")
    store.create_run(record)
    heartbeats: list[str] = []
    original = store.heartbeat_run

    def heartbeat(run_id: str, token: str) -> bool:
        heartbeats.append(token)
        return original(run_id, token)

    store.heartbeat_run = heartbeat  # type: ignore[method-assign]

    async def execute(_item):
        await asyncio.sleep(0.35)

    asyncio.run(
        DurableRunWorker(store, "worker-heartbeat", lambda _item: None).poll_once_async(
            lease_seconds=1, executor=execute
        )
    )
    assert heartbeats


def test_durable_worker_executes_queued_run_through_local_runtime(tmp_path, monkeypatch):
    store = DataStore(tmp_path)
    project = store.create_project("worker-execution")
    record = RunRecord(project_id=project["id"], status="queued")
    store.create_run(record)
    monkeypatch.setattr(
        "sdpstudio_runners.adapters.build_run_command",
        lambda *_args, **_kwargs: (
            ["python", "-c", "print('worker-ok')"],
            ["python", "-c", "print('worker-ok')"],
            None,
        ),
    )
    completed = asyncio.run(
        DurableRunWorker(
            store,
            "worker-execution",
            lambda item: execute_queued_local_run(store, item),
        ).poll_once_async()
    )
    assert completed is not None
    assert store.get_run(record.id)["status"] == "succeeded", store.get_run(record.id).get("error")
    assert store.get_run(record.id)["claim_token"] is None


def test_managed_databricks_execution_persists_update_lifecycle(tmp_path, monkeypatch):
    store = DataStore(tmp_path)
    project = store.create_project("managed-databricks")
    record = RunRecord(project_id=project["id"], status="queued")
    store.create_run(record)
    store.transition_run(record.id, "preparing")
    store.transition_run(record.id, "validating")

    class Adapter:
        async def validate(self, profile, project_path):
            return ValidationResult(True)

        async def submit(self, profile, project_path, run_id, mode, selected):
            return RunHandle(run_id, external_id="update-1")

        async def stream_events(self, handle):
            yield {"state": "completed", "run_id": handle.run_id}

        async def status(self, handle):
            return RunStatus("completed", external_id=handle.external_id)

    monkeypatch.setattr("sdpstudio_runners.adapters.adapter_for", lambda profile: Adapter())
    asyncio.run(
        __import__("sdpstudio_runners.local", fromlist=["LocalRuntime"])
        .LocalRuntime(store)
        .execute_managed_databricks(
            record.id, project["id"], {"adapter": "databricks", "config": {}}, "incremental", []
        )
    )
    assert store.get_run(record.id)["status"] == "succeeded", store.get_run(record.id).get("error")
    assert any(event["kind"] == "status" for event in store.run_events(record.id))
