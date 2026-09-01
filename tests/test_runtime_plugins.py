from types import SimpleNamespace

import pytest
from sdpstudio_runners import adapters
from sdpstudio_server import storage


class PluginAdapter:
    name = "warehouse"
    manifest = {
        "api_version": "v1",
        "license": "MIT",
        "min_sdpstudio_version": "0.1.0",
        "plugin_version": "1.0.0",
        "capabilities": ["runtime"],
    }

    def __init__(self, profile):
        self.profile = profile

    def probe(self, profile):
        return SimpleNamespace(available=True)

    def command(self, profile, **kwargs):
        return ["warehouse-run"], ["warehouse-run"], None


def test_runtime_plugin_discovery_and_factory_isolation(monkeypatch):
    good = SimpleNamespace(name="warehouse", load=lambda: PluginAdapter)
    bad = SimpleNamespace(name="broken", load=lambda: (_ for _ in ()).throw(RuntimeError("broken")))
    monkeypatch.setattr(
        adapters.metadata, "entry_points", lambda: SimpleNamespace(select=lambda group: [good, bad])
    )
    assert "warehouse" in adapters.discover_runtime_plugins()
    assert isinstance(adapters.adapter_for({"adapter": "warehouse", "config": {}}), PluginAdapter)
    with pytest.raises(ValueError, match="Unsupported"):
        adapters.adapter_for({"adapter": "missing"})


def test_runtime_profile_persistence_accepts_discovered_plugin(monkeypatch, tmp_path):
    monkeypatch.setattr(adapters, "discover_runtime_plugins", lambda: {"warehouse": PluginAdapter})
    store = storage.DataStore(tmp_path)
    profile = store.create_runtime_profile("Warehouse", "warehouse", {})
    assert profile["adapter"] == "warehouse"
