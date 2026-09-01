"""Provider-neutral discovery for optional Studio extension points."""

from __future__ import annotations

from importlib import metadata
from typing import Any

from .plugin_contract import validate_plugin_manifest

PLUGIN_GROUPS = {
    "operator": "sdpstudio.operator_definitions",
    "runtime-adapter": "sdpstudio.runtime_adapters",
    "git-provider": "sdpstudio.git_providers",
    "catalog": "sdpstudio.catalogs",
    "importer": "sdpstudio.importers",
    "diagnostic-rule-pack": "sdpstudio.diagnostic_rule_packs",
}


def discover_plugins(kind: str) -> dict[str, Any]:
    """Load compatible plugins for an extension kind without breaking startup."""
    try:
        group = PLUGIN_GROUPS[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown plugin kind: {kind}") from exc
    try:
        entries: Any = metadata.entry_points()
        selected = (
            entries.select(group=group) if hasattr(entries, "select") else entries.get(group, [])
        )
    except Exception:
        return {}
    discovered: dict[str, Any] = {}
    for entry in selected:
        identifier = str(getattr(entry, "name", "unknown"))
        try:
            plugin = entry.load()
            manifest = getattr(plugin, "manifest", None)
            if manifest is None and isinstance(plugin, dict):
                manifest = plugin.get("manifest", plugin)
            if not isinstance(manifest, dict) or not validate_plugin_manifest(
                manifest, identifier=identifier
            ):
                continue
            name = str(getattr(plugin, "name", manifest.get("name", identifier)))
            if name and name not in discovered:
                discovered[name] = plugin
        except Exception:
            continue
    return discovered
