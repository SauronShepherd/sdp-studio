from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Protocol

from sdpstudio_core.models import RuntimeCapabilities
from sdpstudio_core.plugin_contract import validate_plugin_manifest

from .profiles import build_run_command, probe_profile


@dataclass(frozen=True)
class AdapterProbe:
    adapter: str
    capabilities: RuntimeCapabilities
    available: bool
    reason: str | None = None


@dataclass(frozen=True)
class RunHandle:
    run_id: str
    external_id: str | None = None

    @property
    def id(self) -> str:
        """Compatibility alias for the persisted run record boundary."""
        return self.run_id


@dataclass(frozen=True)
class RunStatus:
    state: str
    message: str | None = None
    external_id: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    problems: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class PreviewResult:
    rows: tuple[dict[str, Any], ...] = ()
    schema: tuple[dict[str, Any], ...] = ()
    metrics: dict[str, Any] | None = None


class RuntimeAdapter(Protocol):
    """Uniform asynchronous runtime contract from spec §12.1."""

    name: str

    async def probe(self, profile: dict[str, Any]) -> AdapterProbe: ...

    async def validate(self, profile: dict[str, Any], project: Path) -> ValidationResult: ...

    async def preview(
        self, profile: dict[str, Any], project: Path, node_id: str, limit: int
    ) -> PreviewResult: ...

    async def submit(
        self, profile: dict[str, Any], project: Path, run_id: str, mode: str, selected: list[str]
    ) -> RunHandle: ...

    async def cancel(self, handle: RunHandle) -> None: ...

    async def status(self, handle: RunHandle) -> RunStatus: ...

    async def stream_events(self, handle: RunHandle) -> AsyncIterator[dict[str, Any]]: ...

    async def collect_artifacts(self, handle: RunHandle) -> list[dict[str, Any]]: ...


class CommandRuntimeAdapter(Protocol):
    """Synchronous internal command contract retained during adapter migration."""

    name: str

    def probe(self, profile: dict[str, Any]) -> AdapterProbe: ...

    def command(
        self,
        profile: dict[str, Any],
        *,
        project: Path,
        run_id: str,
        mode: str,
        selected: list[str],
    ) -> tuple[list[str], list[str], Path | None]: ...


class ProfileRuntimeAdapter:
    """Common contract wrapper shared by local and remote profile execution."""

    def __init__(self, name: str):
        self.name = name

    def probe(self, profile: dict[str, Any]) -> AdapterProbe:
        capabilities = probe_profile(profile)
        return AdapterProbe(
            adapter=self.name,
            capabilities=capabilities,
            available=capabilities.available,
            reason=None if capabilities.available else "Runtime prerequisites are unavailable",
        )

    def command(
        self,
        profile: dict[str, Any],
        *,
        project: Path,
        run_id: str,
        mode: str,
        selected: list[str],
    ) -> tuple[list[str], list[str], Path | None]:
        if profile.get("adapter", "local") != self.name:
            raise ValueError(f"Profile adapter is not {self.name!r}")
        return build_run_command(
            profile, project=project, run_id=run_id, mode=mode, selected=selected
        )


class LocalRuntimeAdapter:
    """Concrete async adapter for command-backed local Spark execution."""

    name = "local"

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._statuses: dict[str, RunStatus] = {}
        self._events: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}

    async def probe(self, profile: dict[str, Any]) -> AdapterProbe:
        return await asyncio.to_thread(ProfileRuntimeAdapter(self.name).probe, profile)

    async def validate(self, profile: dict[str, Any], project: Path) -> ValidationResult:
        try:
            await asyncio.to_thread(
                ProfileRuntimeAdapter(self.name).command,
                profile,
                project=project,
                run_id="validation",
                mode="incremental",
                selected=[],
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return ValidationResult(
                False, ({"code": "SDPS-RUNTIME-VALIDATION", "message": str(exc)},)
            )
        return ValidationResult(True)

    async def preview(
        self, profile: dict[str, Any], project: Path, node_id: str, limit: int
    ) -> PreviewResult:
        if limit < 1 or limit > 200:
            raise ValueError("Preview limit must be between 1 and 200")
        validation = await self.validate(profile, project)
        if not validation.valid:
            return PreviewResult()
        return PreviewResult(metrics={"node_id": node_id, "limit": limit, "isolated": True})

    async def submit(
        self, profile: dict[str, Any], project: Path, run_id: str, mode: str, selected: list[str]
    ) -> RunHandle:
        command, _safe, _temp_spec = await asyncio.to_thread(
            ProfileRuntimeAdapter(self.name).command,
            profile,
            project=project,
            run_id=run_id,
            mode=mode,
            selected=selected,
        )
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._events[run_id] = queue
        self._statuses[run_id] = RunStatus("submitted")

        async def execute() -> None:
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=str(project),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                self._statuses[run_id] = RunStatus("running")
                assert process.stdout is not None
                async for raw_line in process.stdout:
                    await queue.put(
                        {"run_id": run_id, "line": raw_line.decode(errors="replace").rstrip()}
                    )
                exit_code = await process.wait()
                self._statuses[run_id] = RunStatus(
                    "succeeded" if exit_code == 0 else "failed", str(exit_code)
                )
            except asyncio.CancelledError:
                raise
            except OSError as exc:
                self._statuses[run_id] = RunStatus("failed", str(exc))
            finally:
                await queue.put(None)

        self._tasks[run_id] = asyncio.create_task(execute())
        return RunHandle(run_id)

    async def cancel(self, handle: RunHandle) -> None:
        task = self._tasks.get(handle.run_id)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self._statuses[handle.run_id] = RunStatus("cancelled")
            await self._events[handle.run_id].put(None)

    async def status(self, handle: RunHandle) -> RunStatus:
        return self._statuses.get(handle.run_id, RunStatus("unknown"))

    async def stream_events(self, handle: RunHandle) -> AsyncIterator[dict[str, Any]]:
        queue = self._events.get(handle.run_id)
        if queue is None:
            return
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

    async def collect_artifacts(self, handle: RunHandle) -> list[dict[str, Any]]:
        return []


class DurableLocalRuntimeAdapter:
    """Async adapter facade over the persisted local runtime.

    ``LocalRuntime`` owns the database-backed run state machine and process
    recovery.  This facade translates that implementation into the uniform
    adapter contract so callers do not need to know the legacy server method
    signatures.  It deliberately delegates execution to the durable runtime;
    it does not create a second in-memory queue.
    """

    name = "local"

    def __init__(self, runtime: Any):
        self.runtime = runtime

    def _project_id(self, project: Path) -> str:
        resolved = project.resolve()
        for record in self.runtime.store.list_projects():
            if Path(record["path"]).resolve() == resolved:
                return str(record["id"])
        raise ValueError(f"Project is not registered: {project}")

    async def probe(self, profile: dict[str, Any]) -> AdapterProbe:
        return await asyncio.to_thread(ProfileRuntimeAdapter(self.name).probe, profile)

    async def validate(self, profile: dict[str, Any], project: Path) -> ValidationResult:
        result = await self.runtime.dry_run(self._project_id(project), profile)
        return ValidationResult(
            bool(result.get("ok")),
            tuple(result.get("problems") or ()),
        )

    async def preview(
        self, profile: dict[str, Any], project: Path, node_id: str, limit: int
    ) -> PreviewResult:
        project_id = self._project_id(project)
        result = await self.runtime.preview(project_id, node_id, limit=limit, profile=profile)
        return PreviewResult(
            rows=tuple(result.get("rows") or ()),
            schema=tuple(
                result.get("schema", {}).get("fields", ())
                if isinstance(result.get("schema"), dict)
                else ()
            ),
            metrics=result.get("profile") or result.get("metrics"),
        )

    async def submit(
        self, profile: dict[str, Any], project: Path, run_id: str, mode: str, selected: list[str]
    ) -> RunHandle:
        project_id = self._project_id(project)
        record = await asyncio.to_thread(
            self.runtime.submit,
            project_id,
            mode,
            selected,
            profile,
            defer_execution=True,
        )
        return RunHandle(record.id, external_id=run_id)

    async def cancel(self, handle: RunHandle) -> None:
        await self.runtime.cancel(handle.run_id)

    async def status(self, handle: RunHandle) -> RunStatus:
        record = self.runtime.store.get_run(handle.run_id)
        return RunStatus(str(record.get("status", "unknown")), record.get("error"))

    async def stream_events(self, handle: RunHandle) -> AsyncIterator[dict[str, Any]]:
        sequence = 0
        while True:
            events = await asyncio.to_thread(self.runtime.store.run_events, handle.run_id, sequence)
            for event in events:
                sequence = int(event.get("seq", sequence))
                yield event
            status = await self.status(handle)
            if status.state in {"succeeded", "validation_failed", "failed", "cancelled", "lost"}:
                return
            await asyncio.sleep(0.25)

    async def collect_artifacts(self, handle: RunHandle) -> list[dict[str, Any]]:
        record = self.runtime.store.get_run(handle.run_id)
        project = self.runtime.store.project_path(record["project_id"])
        root = project / ".sdpstudio" / "runtime" / "run-artifacts" / handle.run_id
        if not root.exists():
            return []
        return [
            {"path": str(path.relative_to(project)).replace("\\", "/"), "size": path.stat().st_size}
            for path in sorted(root.rglob("*"))
            if path.is_file()
        ]


class DatabricksRuntimeAdapter:
    """Async runtime boundary for managed Databricks pipelines."""

    name = "databricks"

    def __init__(self, adapter: Any):
        self.adapter = adapter

    async def probe(self, profile: dict[str, Any]) -> AdapterProbe:
        capabilities = await asyncio.to_thread(self.adapter.probe)
        return AdapterProbe(
            self.name,
            capabilities,
            capabilities.available,
            None if capabilities.available else "Databricks workspace is unavailable",
        )

    async def validate(self, profile: dict[str, Any], project: Path) -> ValidationResult:
        try:
            result = await asyncio.to_thread(self.adapter.validate)
        except (RuntimeError, ValueError) as exc:
            return ValidationResult(
                False, ({"code": "SDPS-DATABRICKS-VALIDATE", "message": str(exc)},)
            )
        return ValidationResult(bool(result.get("valid", True)))

    async def preview(
        self, profile: dict[str, Any], project: Path, node_id: str, limit: int
    ) -> PreviewResult:
        raise RuntimeError("Databricks managed preview requires a submitted pipeline update")

    async def submit(
        self, profile: dict[str, Any], project: Path, run_id: str, mode: str, selected: list[str]
    ) -> RunHandle:
        definition = {"name": project.name, "mode": mode}
        synchronized = await asyncio.to_thread(self.adapter.synchronize, project, definition)
        started = await asyncio.to_thread(
            self.adapter.start,
            full_refresh=mode in {"full-refresh", "full-refresh-all"},
            selected=selected,
        )
        return RunHandle(
            run_id,
            external_id=str(started.get("update_id") or synchronized["pipeline"].get("update_id")),
        )

    async def cancel(self, handle: RunHandle) -> None:
        if not handle.external_id:
            return
        await asyncio.to_thread(self.adapter.cancel, handle.external_id)

    async def status(self, handle: RunHandle) -> RunStatus:
        if not handle.external_id:
            return RunStatus("unknown")
        result = await asyncio.to_thread(self.adapter.status, handle.external_id)
        state = str(result.get("state") or result.get("status") or "unknown").lower()
        return RunStatus(state, external_id=handle.external_id)

    async def stream_events(self, handle: RunHandle) -> AsyncIterator[dict[str, Any]]:
        page_token: str | None = None
        while True:
            events = {}
            if handle.external_id and callable(getattr(self.adapter, "events", None)):
                events = await asyncio.to_thread(
                    self.adapter.events, handle.external_id, page_token=page_token
                )
            emitted = False
            for event in events.get("events", []) if isinstance(events, dict) else []:
                emitted = True
                yield {"run_id": handle.run_id, "kind": "databricks_event", "event": event}
            page_token = events.get("next_page_token") if isinstance(events, dict) else None
            status = await self.status(handle)
            if not emitted:
                yield {"run_id": handle.run_id, "kind": "status", "state": status.state}
            if status.state in {
                "completed",
                "succeeded",
                "failed",
                "cancelled",
                "canceled",
                "error",
            }:
                return
            await asyncio.sleep(1)

    async def collect_artifacts(self, handle: RunHandle) -> list[dict[str, Any]]:
        return []


@dataclass(frozen=True)
class KubernetesLifecycle:
    """Safe native kubectl command contract for a submitted Spark driver."""

    namespace: str
    driver_name: str
    kubectl: str = "kubectl"

    def __post_init__(self) -> None:
        for label, value in (("namespace", self.namespace), ("driver_name", self.driver_name)):
            if not value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,62}", value):
                raise ValueError(f"Invalid Kubernetes {label}")

    def status_command(self) -> tuple[list[str], list[str]]:
        command = [self.kubectl, "-n", self.namespace, "get", "pod", self.driver_name, "-o", "json"]
        return command, [
            self.kubectl,
            "-n",
            self.namespace,
            "get",
            "pod",
            self.driver_name,
            "-o",
            "json",
        ]

    def logs_command(self, *, tail: int = 200, follow: bool = False) -> tuple[list[str], list[str]]:
        if tail < 1 or tail > 10_000:
            raise ValueError("Kubernetes log tail must be between 1 and 10000")
        command = [
            self.kubectl,
            "-n",
            self.namespace,
            "logs",
            self.driver_name,
            "--tail",
            str(tail),
        ]
        if follow:
            command.append("--follow")
        return command, list(command)

    def cancel_command(self, *, grace_period: int = 30) -> tuple[list[str], list[str]]:
        if grace_period < 0 or grace_period > 3_600:
            raise ValueError("Kubernetes grace period is out of range")
        command = [
            self.kubectl,
            "-n",
            self.namespace,
            "delete",
            "pod",
            self.driver_name,
            "--grace-period",
            str(grace_period),
        ]
        return command, list(command)

    def events_command(self) -> tuple[list[str], list[str]]:
        command = [
            self.kubectl,
            "-n",
            self.namespace,
            "get",
            "events",
            "--field-selector",
            f"involvedObject.name={self.driver_name}",
            "-o",
            "json",
        ]
        return command, list(command)

    def executor_pods_command(self) -> tuple[list[str], list[str]]:
        """List executor pods using Spark's stable application selector."""
        command = [
            self.kubectl,
            "-n",
            self.namespace,
            "get",
            "pods",
            "-l",
            f"spark-app-selector=spark-{self.driver_name}",
            "-o",
            "json",
        ]
        return command, list(command)

    def access_check_command(self) -> tuple[list[str], list[str]]:
        """Check cluster connectivity and the minimum driver-pod RBAC permission."""
        command = [
            self.kubectl,
            "-n",
            self.namespace,
            "auth",
            "can-i",
            "get",
            "pods",
        ]
        return command, list(command)

    def access_check_commands(self) -> list[tuple[str, list[str], list[str]]]:
        """Return the minimum pod permissions required for complete lifecycle control."""
        return [
            (
                verb,
                [self.kubectl, "-n", self.namespace, "auth", "can-i", verb, "pods"],
                [self.kubectl, "-n", self.namespace, "auth", "can-i", verb, "pods"],
            )
            for verb in ("get", "list", "watch", "create", "delete")
        ] + [
            (
                "logs",
                [self.kubectl, "-n", self.namespace, "auth", "can-i", "get", "pods/log"],
                [self.kubectl, "-n", self.namespace, "auth", "can-i", "get", "pods/log"],
            )
        ]


RUNTIME_PLUGIN_GROUP = "sdpstudio.runtime_adapters"


def discover_runtime_plugins() -> dict[str, Any]:
    """Discover optional runtime factories; invalid plugins are isolated."""
    try:
        entries: Any = metadata.entry_points()
        selected = (
            entries.select(group=RUNTIME_PLUGIN_GROUP)
            if hasattr(entries, "select")
            else entries.get(RUNTIME_PLUGIN_GROUP, [])
        )
    except Exception:
        return {}
    plugins: dict[str, Any] = {}
    for entry in selected:
        try:
            factory = entry.load()
            name = str(getattr(factory, "name", entry.name))
            manifest = getattr(factory, "manifest", {})
            if not isinstance(manifest, dict) or not validate_plugin_manifest(
                manifest, identifier=name
            ):
                continue
            if not name or name in {"local", "spark-connect", "kubernetes", "databricks-connect"}:
                continue
            instance = factory({"adapter": name, "config": {}})
            if not all(
                callable(getattr(instance, method, None)) for method in ("probe", "command")
            ):
                continue
            plugins[name] = factory
        except Exception:
            continue
    return plugins


def adapter_for(profile: dict[str, Any]) -> Any:
    name = str(profile.get("adapter", "local"))
    if name == "databricks":
        from sdpstudio_adapters_databricks import (
            DatabricksAdapter,
            DatabricksConfig,
            DatabricksRestClient,
        )

        config = DatabricksConfig.from_mapping(profile.get("config", {}))
        return DatabricksRuntimeAdapter(DatabricksAdapter(config, DatabricksRestClient(config)))
    if name not in {"local", "spark-connect", "kubernetes", "databricks-connect"}:
        factory = discover_runtime_plugins().get(name)
        if factory is None:
            raise ValueError(f"Unsupported runtime adapter: {name}")
        return factory(profile)
    return ProfileRuntimeAdapter(name)
