import asyncio
from pathlib import Path

from sdpstudio_runners.adapters import RunHandle
from sdpstudio_server.runtime_dispatch import RuntimeDispatch


def test_runtime_dispatch_awaits_blocking_submit_and_cancel():
    calls = []

    class Implementation:
        def submit(self, project_id, **kwargs):
            calls.append(("submit", project_id, kwargs))
            return {"id": "run-1"}

        def cancel(self, run_id):
            calls.append(("cancel", run_id))
            return True

    async def exercise():
        dispatch = RuntimeDispatch(Implementation())
        submitted = await dispatch.submit("project-1", mode="incremental")
        cancelled = await dispatch.cancel("run-1")
        return submitted, cancelled

    assert asyncio.run(exercise()) == ({"id": "run-1"}, True)
    assert calls == [("submit", "project-1", {"mode": "incremental"}), ("cancel", "run-1")]


def test_runtime_dispatch_routes_through_async_adapter_contract(tmp_path: Path):
    calls = []

    class Store:
        def project_path(self, project_id):
            assert project_id == "project-1"
            return tmp_path

    class Implementation:
        store = Store()

    class Adapter:
        async def submit(self, profile, project, run_id, mode, selected):
            calls.append((profile, project, run_id, mode, selected))
            return RunHandle("run-adapter")

        async def cancel(self, handle):
            calls.append(("cancel", handle.id))

    async def exercise():
        dispatch = RuntimeDispatch(Implementation(), adapter=Adapter())
        submitted = await dispatch.submit(
            "project-1", "incremental", ["node-1"], profile={"adapter": "local"}
        )
        cancelled = await dispatch.cancel(submitted.id)
        return submitted, cancelled

    submitted, cancelled = asyncio.run(exercise())
    assert submitted.id == "run-adapter"
    assert cancelled is True
    assert calls == [
        ({"adapter": "local"}, tmp_path, "", "incremental", ["node-1"]),
        ("cancel", "run-adapter"),
    ]


def test_runtime_dispatch_routes_preview_and_dry_run_through_async_contract(tmp_path: Path):
    calls = []

    class Store:
        def project_path(self, project_id):
            return tmp_path

    class Implementation:
        store = Store()

    class Result:
        rows = ({"value": 1},)
        schema = ({"name": "value"},)
        metrics = {"rows": 1}

    class Validation:
        valid = True
        problems = ()

    class Adapter:
        async def preview(self, profile, project, node_id, limit):
            calls.append(("preview", profile, project, node_id, limit))
            return Result()

        async def validate(self, profile, project):
            calls.append(("validate", profile, project))
            return Validation()

    async def exercise():
        dispatch = RuntimeDispatch(Implementation(), adapter=Adapter())
        preview = await dispatch.preview(
            "project-1", "node-1", limit=12, profile={"adapter": "local"}
        )
        dry_run = await dispatch.dry_run("project-1", profile={"adapter": "local"})
        return preview, dry_run

    preview, dry_run = asyncio.run(exercise())
    assert preview["rows"] == [{"value": 1}]
    assert dry_run == {"ok": True, "problems": []}
    assert [call[0] for call in calls] == ["preview", "validate"]


def test_runtime_dispatch_resolves_non_local_profile_adapter(tmp_path: Path):
    calls = []

    class Store:
        def project_path(self, project_id):
            return tmp_path

    class Implementation:
        store = Store()

    class Adapter:
        async def submit(self, profile, project, run_id, mode, selected):
            calls.append((profile["adapter"], project, mode))
            return RunHandle("remote-run")

    async def exercise():
        dispatch = RuntimeDispatch(
            Implementation(),
            adapter=None,
            adapter_factory=lambda profile: Adapter(),
        )
        return await dispatch.submit(
            "project-1", "incremental", [], profile={"adapter": "databricks"}
        )

    result = asyncio.run(exercise())
    assert result.id == "remote-run"
    assert calls == [("databricks", tmp_path, "incremental")]
