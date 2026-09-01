from pathlib import Path

import pytest
from sdpstudio_adapters_databricks import (
    DatabricksAdapter,
    DatabricksConfig,
    DatabricksRestClient,
)
from sdpstudio_runners.adapters import DatabricksRuntimeAdapter


class FakeClient:
    def probe(self):
        return {"available": True, "spark_version": "4.2.0"}

    def upload_source(self, source_root: Path):
        return {"path": str(source_root), "digest": "abc"}

    def upsert_pipeline(self, definition):
        return {"pipeline_id": "p-1", "definition": definition}

    def validate(self, pipeline_id):
        return {"pipeline_id": pipeline_id, "valid": True}

    def start(self, pipeline_id, *, full_refresh=False, selected=None):
        return {
            "update_id": "u-1",
            "pipeline_id": pipeline_id,
            "full_refresh": full_refresh,
            "selected": selected,
        }

    def get_update(self, update_id):
        return {"update_id": update_id, "state": "COMPLETED"}

    def cancel(self, update_id):
        return {"update_id": update_id, "cancelled": True}


def test_databricks_adapter_isolated_lifecycle():
    adapter = DatabricksAdapter(DatabricksConfig("https://workspace.example", "p-1"), FakeClient())
    assert adapter.probe().available
    assert adapter.validate()["valid"]
    assert adapter.start(full_refresh=True, selected=["orders"])["update_id"] == "u-1"
    assert adapter.status("u-1")["state"] == "COMPLETED"
    assert adapter.cancel("u-1")["cancelled"]


def test_databricks_config_rejects_implicit_or_missing_workspace():
    with pytest.raises(ValueError):
        DatabricksConfig.from_mapping({"workspace_url": "workspace.example"})


def test_databricks_rest_client_maps_pipeline_lifecycle_without_network(tmp_path: Path):
    calls = []

    def request(method, path, payload):
        calls.append((method, path, payload))
        if path == "/api/2.0/pipelines":
            return {"statuses": []}
        if path.startswith("/api/2.0/pipelines/updates/u-1/events"):
            return {"events": [{"event_type": "FLOW_PROGRESS"}], "next_page_token": "next token"}
        return {"update_id": "u-1", "state": "COMPLETED"}

    source = tmp_path / "transformations" / "orders.py"
    source.parent.mkdir()
    source.write_text("print('safe')\n", encoding="utf-8")
    (tmp_path / ".env").write_text("TOKEN=do-not-upload\n", encoding="utf-8")
    metadata = tmp_path / ".sdpstudio"
    metadata.mkdir()
    (metadata / "project.yaml").write_text("name: private\n", encoding="utf-8")
    (tmp_path / "service-token.txt").write_text("do-not-upload\n", encoding="utf-8")
    config = DatabricksConfig(
        "https://workspace.example", "p-1", source_root="/Workspace/Shared/sdpstudio/test"
    )
    client = DatabricksRestClient(config, token="token-value", request=request)
    assert client.probe()["available"] is True
    upload = client.upload_source(tmp_path)
    assert upload["files"] == ["transformations/orders.py"]
    assert "token-value" not in repr(calls)
    assert client.start("p-1", full_refresh=True, selected=["orders"])["update_id"] == "u-1"
    assert client.events("u-1", page_token="next token")["events"]
    assert calls[-1][1].endswith("page_token=next%20token")
    assert client.get_update("u-1")["state"] == "COMPLETED"
    assert client.cancel("u-1")["update_id"] == "u-1"
    assert calls[-1] == ("POST", "/api/2.0/pipelines/updates/u-1/cancel", {})


def test_databricks_rest_client_requires_token_when_using_real_transport(monkeypatch):
    monkeypatch.delenv("SDPSTUDIO_DATABRICKS_TOKEN", raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    client = DatabricksRestClient(DatabricksConfig("https://workspace.example"))
    assert client.probe() == {"available": False, "sdp": False}


@pytest.mark.asyncio
async def test_databricks_runtime_adapter_uses_common_async_lifecycle(tmp_path: Path):
    class Adapter:
        def __init__(self):
            self.started = False

        def probe(self):
            return type("Capabilities", (), {"available": True})()

        def validate(self):
            return {"valid": True}

        def synchronize(self, project, definition):
            return {"pipeline": {"id": "p-1"}}

        def start(self, *, full_refresh=False, selected=None):
            self.started = True
            return {"update_id": "u-1"}

        def status(self, update_id):
            return {"state": "COMPLETED"}

        def cancel(self, update_id):
            return {"update_id": update_id}

    adapter = DatabricksRuntimeAdapter(Adapter())
    assert (await adapter.probe({"adapter": "databricks"})).available
    assert (await adapter.validate({}, tmp_path)).valid
    handle = await adapter.submit({}, tmp_path, "run-1", "full-refresh", ["orders"])
    assert handle.external_id == "u-1"
    assert (await adapter.status(handle)).state == "completed"
    events = [event async for event in adapter.stream_events(handle)]
    assert events[-1]["state"] == "completed"
    await adapter.cancel(handle)
