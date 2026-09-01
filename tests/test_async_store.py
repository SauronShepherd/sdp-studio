import pytest
from sdpstudio_core.models import RunRecord
from sdpstudio_server.async_store import AsyncStore
from sdpstudio_server.runtime_profile_service import validate_runtime_profile
from sdpstudio_server.storage import DataStore


class FakeStore:
    def list_projects(self, prefix: str = ""):
        return [prefix or "project"]


def test_runtime_profile_validation_is_shared_outside_datastore():
    validate_runtime_profile("local", {"mode": "local"})
    with pytest.raises(ValueError, match="secret literal"):
        validate_runtime_profile("local", {"token": "plaintext"})


@pytest.mark.asyncio
async def test_sqlite_runtime_profile_path_does_not_call_private_store_validator(tmp_path):
    store = DataStore(tmp_path)
    store._validate_runtime_profile = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("private compatibility validator was called")
    )
    async_store = AsyncStore(store)
    try:
        profile = await async_store.call(
            "create_runtime_profile", "local profile", "local", {"mode": "local"}
        )
        assert profile["adapter"] == "local"
    finally:
        await async_store.close()


@pytest.mark.asyncio
async def test_async_store_moves_store_calls_through_async_boundary():
    store = AsyncStore(FakeStore())
    assert await store.call("list_projects", prefix="orders") == ["orders"]


@pytest.mark.asyncio
async def test_compatibility_boundary_runs_unmigrated_calls_off_loop():
    from sdpstudio_server.compatibility_store import CompatibilityStoreBoundary

    assert await CompatibilityStoreBoundary(FakeStore()).call("list_projects") == ["project"]


@pytest.mark.asyncio
async def test_async_store_health_check_uses_compatibility_fallback():
    class HealthyStore:
        def health_check(self):
            return True

    assert await AsyncStore(HealthyStore()).call("health_check") is True


@pytest.mark.asyncio
async def test_async_store_reads_projects_through_sqlalchemy_sqlite_engine(tmp_path):
    store = DataStore(tmp_path)
    created = store.create_project("orders")
    async_store = AsyncStore(store)
    try:
        assert await async_store.call("health_check") is True
        projects = await async_store.call("list_projects")
        assert projects[0]["id"] == created["id"]
        assert (await async_store.call("get_project_row", created["id"]))["name"] == "orders"
        await async_store.call(
            "append_audit_event", "tester", "project.read", "project", created["id"]
        )
        run = RunRecord(project_id=created["id"])
        store.create_run(run)
        snapshot = await async_store.call(
            "save_node_snapshot",
            run.id,
            "node-1",
            schema=[{"name": "id", "type": "long"}],
        )
        assert snapshot["node_id"] == "node-1"
        schedule = store.create_schedule(created["id"], "daily", "0 0 * * *")
        assert await async_store.call("claim_schedule", schedule["id"], "2026-01-01T00:00") is True
        assert await async_store.call("claim_schedule", schedule["id"], "2026-01-01T00:00") is False
        event = await async_store.call(
            "append_collaboration_event", created["id"], {"type": "y_update", "update": "AQID"}
        )
        assert event["seq"] == 1
        assert (await async_store.call("collaboration_events", created["id"]))[0]["seq"] == 1
        snapshot = await async_store.call(
            "save_collaboration_snapshot", created["id"], {"format": "yjs-update-bundle"}, seq=1
        )
        assert snapshot["seq"] == 1
        for index in range(99):
            await async_store.call(
                "append_collaboration_event",
                created["id"],
                {"type": "y_update", "update": str(index)},
            )
        compacted = await async_store.call("collaboration_snapshot", created["id"])
        assert compacted is not None
        assert compacted["seq"] == 100
        assert compacted["document"]["format"] == "yjs-update-bundle"
        assert await async_store.call("collaboration_events", created["id"], after=0) == []
    finally:
        await async_store.close()
