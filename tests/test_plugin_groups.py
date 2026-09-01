from types import SimpleNamespace

import pytest
from sdpstudio_core import PLUGIN_GROUPS, discover_plugins, plugins


def test_all_specified_extension_groups_are_registered():
    assert {
        "operator",
        "runtime-adapter",
        "git-provider",
        "catalog",
        "importer",
        "diagnostic-rule-pack",
    } == set(PLUGIN_GROUPS)


def test_generic_plugin_discovery_validates_manifest_and_isolates_broken_entries(monkeypatch):
    good_plugin = SimpleNamespace(
        name="catalog.test",
        manifest={
            "api_version": "v1",
            "license": "MIT",
            "min_sdpstudio_version": "0.1.0",
            "plugin_version": "1.0.0",
            "capabilities": ["catalog"],
        },
    )
    good = SimpleNamespace(name="catalog.test", load=lambda: good_plugin)
    bad = SimpleNamespace(name="broken", load=lambda: (_ for _ in ()).throw(RuntimeError("broken")))
    monkeypatch.setattr(
        plugins.metadata,
        "entry_points",
        lambda: SimpleNamespace(select=lambda group: [good, bad]),
    )
    assert discover_plugins("catalog") == {"catalog.test": good_plugin}


def test_generic_plugin_discovery_rejects_unknown_kind():
    with pytest.raises(ValueError, match="Unknown plugin kind"):
        discover_plugins("unknown")


def test_plugin_inventory_route_exposes_all_extension_kinds(tmp_path):
    from fastapi.testclient import TestClient
    from sdpstudio_server.app import create_app

    response = TestClient(create_app(tmp_path)).get("/api/plugins")
    assert response.status_code == 200
    assert set(response.json()) == set(PLUGIN_GROUPS)
