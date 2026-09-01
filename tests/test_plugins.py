from types import SimpleNamespace

from sdpstudio_core import operators


def test_operator_plugin_discovery_validates_and_isolates_failures(monkeypatch):
    good = SimpleNamespace(
        load=lambda: (
            lambda: {
                "id": "plugin.test",
                "title": "Plugin",
                "inputs": ["in"],
                "outputs": ["out"],
                "api_version": "v1",
                "license": "MIT",
                "plugin_version": "1.0.0",
                "capabilities": ["operators"],
            }
        )
    )
    bad = SimpleNamespace(load=lambda: (_ for _ in ()).throw(RuntimeError("broken plugin")))
    monkeypatch.setattr(
        operators.metadata,
        "entry_points",
        lambda: SimpleNamespace(select=lambda group: [good, bad]),
    )
    discovered = operators.discover_operator_plugins()
    assert [item["id"] for item in discovered] == ["plugin.test"]
    assert operators.operator_catalog()["plugin.test"]["title"] == "Plugin"
    assert operators.builtin_registry().get("plugin.test").category == "Extensions"


def test_plugin_manifest_rejects_incompatible_versions():
    from sdpstudio_core.plugin_contract import validate_plugin_manifest

    assert not validate_plugin_manifest(
        {"api_version": "v2", "license": "MIT", "plugin_version": "1.0.0", "capabilities": []},
        identifier="bad",
    )
