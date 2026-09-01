"""Deterministic run-comparison calculations independent of HTTP concerns."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sdpstudio_core.debug import profile_diff, schema_diff, schema_fingerprint


def duration_seconds(run: dict[str, Any]) -> float | None:
    if not run.get("started_at") or not run.get("finished_at"):
        return None
    return (
        datetime.fromisoformat(str(run["finished_at"]))
        - datetime.fromisoformat(str(run["started_at"]))
    ).total_seconds()


def stage_metric_deltas(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> dict[str, Any]:
    if not left or not right:
        return {
            "available": False,
            "reason": "Event-summary artifacts are missing for one or both runs.",
        }
    left_stages = {str(item.get("stage_id")): item for item in left.get("stages", [])}
    right_stages = {str(item.get("stage_id")): item for item in right.get("stages", [])}
    return {
        "available": True,
        "stages": [
            {
                "stage_id": stage_id,
                "left": left_stages.get(stage_id),
                "right": right_stages.get(stage_id),
                "shuffle_read_bytes_delta": (
                    right_stages.get(stage_id, {}).get("shuffle_read_bytes", 0)
                    - left_stages.get(stage_id, {}).get("shuffle_read_bytes", 0)
                ),
                "shuffle_write_bytes_delta": (
                    right_stages.get(stage_id, {}).get("shuffle_write_bytes", 0)
                    - left_stages.get(stage_id, {}).get("shuffle_write_bytes", 0)
                ),
            }
            for stage_id in sorted(set(left_stages) | set(right_stages))
        ],
    }


def node_diffs(
    left_items: list[dict[str, Any]], right_items: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    left = {item["node_id"]: item for item in left_items}
    right = {item["node_id"]: item for item in right_items}
    schema_nodes: dict[str, Any] = {}
    quality_nodes: dict[str, Any] = {}
    for node_id in sorted(set(left) | set(right)):
        before = left.get(node_id) or {}
        after = right.get(node_id) or {}
        before_schema, after_schema = before.get("schema"), after.get("schema")
        if before_schema is None or after_schema is None:
            schema_nodes[node_id] = {"available": False, "reason": "schema missing"}
        else:
            schema_nodes[node_id] = {
                "available": True,
                "before_fingerprint": schema_fingerprint(before_schema),
                "after_fingerprint": schema_fingerprint(after_schema),
                "diff": schema_diff(before_schema, after_schema),
            }
        before_profile, after_profile = before.get("profile"), after.get("profile")
        if isinstance(before_profile, dict) and isinstance(after_profile, dict):
            quality_nodes[node_id] = {
                "available": True,
                "diff": profile_diff(before_profile, after_profile),
            }
        else:
            quality_nodes[node_id] = {
                "available": False,
                "reason": "profile metrics missing",
            }
    return schema_nodes, quality_nodes


def schema_timeline(
    runs: list[dict[str, Any]], snapshots_by_run: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Build a deterministic per-node schema timeline from persisted snapshots."""
    previous: dict[str, list[dict[str, Any]]] = {}
    timeline: list[dict[str, Any]] = []
    ordered_runs = sorted(runs, key=lambda item: (str(item.get("created_at", "")), item["id"]))
    for run in ordered_runs:
        run_id = str(run["id"])
        for snapshot in sorted(
            snapshots_by_run.get(run_id, []), key=lambda item: str(item["node_id"])
        ):
            schema = snapshot.get("schema")
            if not isinstance(schema, list):
                continue
            node_id = str(snapshot["node_id"])
            before = previous.get(node_id)
            diff = schema_diff(before, schema) if before is not None else None
            timeline.append(
                {
                    "run_id": run_id,
                    "node_id": node_id,
                    "created_at": run.get("created_at"),
                    "fingerprint": schema_fingerprint(schema),
                    "changed": bool(diff and not diff["compatible"]),
                    "diff": diff,
                }
            )
            previous[node_id] = schema
    return timeline
