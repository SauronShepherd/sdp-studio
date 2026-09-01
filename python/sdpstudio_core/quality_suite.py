"""First-class `.sdpstudio/tests/quality.yaml` suite support."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .quality import evaluate_quality


class QualitySuiteError(ValueError):
    code = "SDPS-QUALITY-001"


_EXECUTION_MODES = {"preview", "post-run", "scheduled"}


def load_quality_suite(path: Path) -> list[dict[str, Any]]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise QualitySuiteError("Unable to read quality suite") from exc
    checks = document.get("checks") if isinstance(document, dict) else None
    if not isinstance(checks, list):
        raise QualitySuiteError("Quality suite must contain a checks list")
    normalized: list[dict[str, Any]] = []
    for index, check in enumerate(checks):
        if (
            not isinstance(check, dict)
            or not isinstance(check.get("id"), str)
            or not isinstance(check.get("type"), str)
        ):
            raise QualitySuiteError(f"Quality check {index} requires id and type")
        config = check.get("config", {})
        if not isinstance(config, dict):
            raise QualitySuiteError(f"Quality check {check['id']} config must be an object")
        mode = check.get("mode", "preview")
        if mode not in _EXECUTION_MODES:
            raise QualitySuiteError(
                f"Quality check {check['id']} mode must be one of: preview, post-run, scheduled"
            )
        normalized.append(
            {"id": check["id"], "type": check["type"], "config": config, "mode": mode}
        )
    return normalized


def execute_quality_suite(
    path: Path, rows_by_check: dict[str, list[dict[str, Any]]], *, mode: str | None = None
) -> dict[str, Any]:
    if mode is not None and mode not in _EXECUTION_MODES:
        raise QualitySuiteError(
            f"Quality suite mode must be one of: {', '.join(sorted(_EXECUTION_MODES))}"
        )
    results = []
    for check in load_quality_suite(path):
        if mode is not None and check["mode"] != mode:
            continue
        result = evaluate_quality(
            check["type"], check["config"], rows_by_check.get(check["id"], [])
        )
        results.append({"id": check["id"], **result})
    return {
        "status": "failed" if any(item["status"] == "failed" for item in results) else "passed",
        "mode": mode or "all",
        "checks": results,
    }
