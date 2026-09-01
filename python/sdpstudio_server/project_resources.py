"""Project-owned filesystem and local-catalog service boundary."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from time import monotonic
from typing import Any

from .catalog import local_catalog
from .filesystem import FileInfo, ProjectFileSystem


class ProjectResourceService:
    """Coordinates safe project-relative files and catalog inspection."""

    def __init__(
        self,
        filesystem: ProjectFileSystem | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        self.filesystem = filesystem or ProjectFileSystem()
        self.workspace_root = workspace_root.resolve() if workspace_root else None
        self._runtime_catalog_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def resolve_project_path(self, row: dict[str, Any]) -> Path:
        """Resolve a persisted project row without permitting workspace escape."""
        if self.workspace_root is None:
            raise ValueError("Project resource service has no workspace root")
        path = Path(row["path"]).resolve()
        if self.workspace_root not in path.parents:
            raise ValueError("Project path escaped workspace root")
        return path

    def workspace_available(self) -> bool:
        return self.workspace_root is not None and self.workspace_root.is_dir()

    def tree(self, project: Path) -> list[FileInfo]:
        return self.filesystem.tree(project)

    def read_text(self, project: Path, relative: str) -> tuple[str, FileInfo]:
        return self.filesystem.read_text(project, relative)

    def write_text(
        self, project: Path, relative: str, content: str, expected_etag: str | None
    ) -> FileInfo:
        return self.filesystem.write_text(project, relative, content, expected_etag)

    def catalog(self, project: Path) -> dict[str, Any]:
        return local_catalog(project)

    def runtime_catalog(
        self, profile: dict[str, Any], project: Path | None = None
    ) -> dict[str, Any]:
        """Discover a catalog through an explicit runtime command or snapshot."""
        profile_id = str(profile.get("id") or profile.get("adapter") or "runtime")
        cached = self._runtime_catalog_cache.get(profile_id)
        if cached and monotonic() - cached[0] < 30:
            return cached[1]
        config: dict[str, Any] = (
            profile["config"] if isinstance(profile.get("config"), dict) else {}
        )
        command = config.get("catalog_command")
        if isinstance(command, list) and command and all(isinstance(item, str) for item in command):
            if any("\x00" in item for item in command):
                raise RuntimeError("SDPS-CATALOG-002: catalog command contains invalid arguments")
            from sdpstudio_runners.process import run_process

            process = asyncio.run(
                run_process(
                    command,
                    cwd=str(project or self.workspace_root or Path.cwd()),
                    timeout=30,
                    max_output_bytes=2 * 1024 * 1024,
                )
            )
            if process.timed_out or process.returncode != 0:
                raise RuntimeError("SDPS-CATALOG-003: runtime catalog discovery failed")
            try:
                discovered = json.loads(process.output)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "SDPS-CATALOG-004: runtime catalog returned invalid JSON"
                ) from exc
            if not isinstance(discovered, dict) or not isinstance(discovered.get("tables"), list):
                raise RuntimeError(
                    "SDPS-CATALOG-005: runtime catalog response has an invalid shape"
                )
            result = {
                "catalog": discovered.get("catalog", profile.get("adapter", "runtime")),
                "namespace": discovered.get("namespace", "default"),
                "tables": discovered["tables"],
                "source": "runtime-command",
            }
            self._runtime_catalog_cache[profile_id] = (monotonic(), result)
            return result
        snapshot = config.get("catalog") if isinstance(config.get("catalog"), dict) else None
        if snapshot is None:
            raise RuntimeError(
                "SDPS-CATALOG-001: selected runtime does not expose catalog discovery"
            )
        result = {
            "catalog": snapshot.get("catalog", profile.get("adapter", "runtime")),
            "namespace": snapshot.get("namespace", "default"),
            "tables": list(snapshot.get("tables", [])),
            "source": "runtime",
        }
        self._runtime_catalog_cache[profile_id] = (monotonic(), result)
        return result

    def create_directory(self, project: Path, relative: str) -> FileInfo:
        return self.filesystem.create_directory(project, relative)

    def delete(self, project: Path, relative: str, expected_etag: str | None = None) -> None:
        self.filesystem.delete(project, relative, expected_etag)

    def rename(
        self, project: Path, old: str, new: str, expected_etag: str | None = None
    ) -> FileInfo:
        return self.filesystem.rename(project, old, new, expected_etag)
