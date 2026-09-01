"""Deterministic debug-bundle entry assembly and redaction."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sdpstudio_core.debug import schema_fingerprint


def build_entries(
    run: dict[str, Any],
    events: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    *,
    artifact_dir: Path,
    project: Path,
    redact_value: Callable[[Any], Any],
    registered_secrets: dict[str, str] | None = None,
    redact_registered: Callable[[str, dict[str, str]], tuple[str, set[str]]] | None = None,
) -> dict[str, bytes]:
    def encoded(value: Any) -> bytes:
        return (
            json.dumps(redact_value(value), indent=2, sort_keys=True, default=str) + "\n"
        ).encode("utf-8")

    entries: dict[str, bytes] = {
        "README.txt": (
            b"SDP Studio debug bundle. Values matching secret fields/patterns are redacted. "
            b"Review business data before sharing.\n"
        ),
        "run.json": encoded(run),
        "events.json": encoded(events),
        "node-snapshots.json": encoded(snapshots),
        "schema-fingerprints.json": (
            json.dumps(
                {
                    str(item["node_id"]): schema_fingerprint(item["schema"])
                    for item in snapshots
                    if item.get("schema") is not None
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
    }
    for name in ("run-snapshot.json", "event-summary.json"):
        source = artifact_dir / name
        if source.exists():
            try:
                entries[name] = encoded(json.loads(source.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                entries[name] = redact_value(source.read_text(encoding="utf-8")).encode("utf-8")
    source_map = project / ".sdpstudio" / "source-maps" / "generated.py.map.json"
    if source_map.exists():
        entries["generated.py.map.json"] = redact_value(
            source_map.read_text(encoding="utf-8")
        ).encode("utf-8")
    plan = artifact_dir / "plan.json"
    if plan.exists():
        entries["plan.json"] = redact_value(plan.read_text(encoding="utf-8")).encode("utf-8")
    if registered_secrets and redact_registered:
        for name, content in list(entries.items()):
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                continue
            entries[name] = redact_registered(text, registered_secrets)[0].encode("utf-8")
    return entries
