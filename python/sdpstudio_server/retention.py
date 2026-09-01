"""Bounded cleanup for project runtime artifacts.

The service is filesystem-only and deliberately constrained to a supplied project
root; database metadata is never deleted implicitly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class RetentionPolicy:
    max_count: int = 100
    max_age_days: int = 30
    sensitive_samples: bool = True

    @classmethod
    def from_env(cls) -> RetentionPolicy:
        def positive(name: str, default: int) -> int:
            raw = os.environ.get(name, str(default))
            try:
                value = int(raw)
            except ValueError as exc:
                raise ValueError(f"{name} must be an integer") from exc
            if value < 1:
                raise ValueError(f"{name} must be positive")
            return value

        return cls(
            max_count=positive("SDPSTUDIO_ARTIFACT_MAX_COUNT", 100),
            max_age_days=positive("SDPSTUDIO_ARTIFACT_MAX_AGE_DAYS", 30),
            sensitive_samples=os.environ.get("SDPSTUDIO_ALLOW_SENSITIVE_SAMPLES", "1") == "1",
        )


def cleanup_runtime_artifacts(
    project_root: Path, policy: RetentionPolicy, *, now: datetime | None = None
) -> dict[str, object]:
    """Remove expired/excess runtime artifacts and return an auditable report."""
    root = project_root.resolve()
    runtime = root / ".sdpstudio" / "runtime"
    categories = (
        "run-artifacts",
        "event-logs",
        "previews",
        "preview-artifacts",
        "debug-bundles",
        "profiles",
    )
    cutoff = (now or datetime.now(UTC)) - timedelta(days=policy.max_age_days)
    removed: list[str] = []
    failures: list[dict[str, str]] = []
    for category in categories:
        directory = runtime / category
        if not directory.is_dir() or directory.is_symlink():
            continue
        items = sorted(
            (item for item in directory.iterdir() if not item.is_symlink()),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for item in items[policy.max_count :]:
            _remove(item, root, removed, failures)
        for item in items[: policy.max_count]:
            try:
                if datetime.fromtimestamp(item.stat().st_mtime, UTC) < cutoff:
                    _remove(item, root, removed, failures)
            except OSError as exc:
                failures.append({"path": str(item), "error": str(exc)})
    return {
        "removed": removed,
        "failures": failures,
        "policy": {
            "max_count": policy.max_count,
            "max_age_days": policy.max_age_days,
            "sensitive_samples": policy.sensitive_samples,
        },
    }


def _remove(path: Path, root: Path, removed: list[str], failures: list[dict[str, str]]) -> None:
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
        if path.is_dir():
            for child in path.iterdir():
                _remove(child, root, removed, failures)
            path.rmdir()
        else:
            path.unlink()
        removed.append(str(path.relative_to(root)).replace("\\", "/"))
    except (OSError, ValueError) as exc:
        failures.append({"path": str(path), "error": str(exc)})
