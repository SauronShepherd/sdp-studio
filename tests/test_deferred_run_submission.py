from sdpstudio_core.models import RuntimeCapabilities
from sdpstudio_runners.local import LocalRuntime
from sdpstudio_server.storage import DataStore


def test_deferred_submission_persists_queued_run_without_in_process_task(tmp_path, monkeypatch):
    capabilities = RuntimeCapabilities(adapter="local", available=True)
    monkeypatch.setattr(
        "sdpstudio_runners.adapters.probe_profile",
        lambda _profile: capabilities,
    )
    monkeypatch.setattr(
        "sdpstudio_runners.adapters.build_run_command",
        lambda *_args, **_kwargs: (["echo", "ok"], ["echo", "ok"], None),
    )
    store = DataStore(tmp_path)
    project = store.create_project("deferred")
    runtime = LocalRuntime(store)
    record = runtime.submit(
        project["id"],
        profile={"adapter": "local", "config": {}},
        defer_execution=True,
    )
    persisted = store.get_run(record.id)
    assert persisted["status"] == "queued"
    assert persisted["command"]
    assert record.id not in runtime.tasks
