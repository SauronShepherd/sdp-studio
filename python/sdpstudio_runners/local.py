from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sdpstudio_codegen import generate_preview_script
from sdpstudio_core.debug import parse_explain_plan, summarize_spark_event_stream
from sdpstudio_core.ids import new_ulid
from sdpstudio_core.models import Problem, RunRecord, RuntimeCapabilities

from .process import run_process

SECRET_MARKERS = ("TOKEN", "PASSWORD", "SECRET", "KEY", "CREDENTIAL", "REMOTE")


def _redacted_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    if extra:
        env.update(extra)
    return env


def redact(text: str, extra_values: list[str] | None = None) -> str:
    value = text
    values = list(extra_values or [])
    for key, secret in os.environ.items():
        if secret and len(secret) >= 8 and any(marker in key.upper() for marker in SECRET_MARKERS):
            values.append(secret)
    for secret in values:
        if secret and len(secret) >= 8:
            value = value.replace(secret, "***REDACTED***")
    # Defense in depth for connection strings accidentally echoed by a child process.
    value = re.sub(r"(?i)(token|password|secret)=([^;\s,&]+)", r"\1=***REDACTED***", value)
    return value


def _safe_runtime_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Persist runtime provenance without copying credential-like configuration values."""

    def scrub(value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {name: scrub(item, str(name)) for name, item in value.items()}
        if isinstance(value, list):
            return [scrub(item, key) for item in value]
        if isinstance(value, str):
            return (
                "***REDACTED***"
                if any(marker in key.upper() for marker in SECRET_MARKERS)
                else redact(value)
            )
        return value

    return scrub(profile)


def probe_local() -> RuntimeCapabilities:
    spark_pipelines = shutil.which("spark-pipelines")
    spark_submit = shutil.which("spark-submit")
    java = shutil.which("java")
    pyspark_pipelines = (
        importlib.util.find_spec("pyspark.pipelines") is not None
        if importlib.util.find_spec("pyspark")
        else False
    )
    spark_version = None
    if importlib.util.find_spec("pyspark"):
        try:
            import pyspark

            spark_version = getattr(pyspark, "__version__", None)
        except Exception:
            spark_version = None
    available = bool(spark_pipelines and pyspark_pipelines and java)
    return RuntimeCapabilities(
        adapter="local",
        available=available,
        spark_version=spark_version,
        sdp=bool(spark_pipelines and pyspark_pipelines),
        append_flow=bool(pyspark_pipelines),
        sink=bool(pyspark_pipelines and (not spark_version or spark_version.startswith("4.2"))),
        selective_refresh=bool(spark_pipelines),
        full_refresh=bool(spark_pipelines),
        spark_connect=bool(spark_pipelines),
        details={
            "python": sys.executable,
            "java": java,
            "spark_pipelines": spark_pipelines,
            "spark_submit": spark_submit,
            "pyspark_pipelines_importable": pyspark_pipelines,
        },
    )


def _load_source_map(project: Path) -> list[dict[str, Any]]:
    path = project / ".sdpstudio" / "source-maps" / "generated.py.map.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [m for m in payload.get("mappings", []) if isinstance(m, dict)]
    except (OSError, ValueError):
        return []


def _node_for_generated_line(
    mappings: list[dict[str, Any]], line_number: int
) -> dict[str, Any] | None:
    candidates = [
        m
        for m in mappings
        if m.get("file") == "transformations/generated.py"
        and int(m.get("start_line", -1)) <= line_number <= int(m.get("end_line", -1))
    ]
    if not candidates:
        return None
    # Prefer the smallest mapped range: a transform line is more specific than the
    # surrounding output definition range.
    return min(candidates, key=lambda m: int(m.get("end_line", 0)) - int(m.get("start_line", 0)))


def _generated_line_from_log(text: str) -> int | None:
    patterns = [
        r"generated\.py[\"']?, line (\d+)",
        r"generated\.py:(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


def _ingest_recent_event_logs(
    project: Path,
    started_epoch: float,
    run_id: str,
    *,
    moderate_skew_ratio: float = 2.0,
    severe_skew_ratio: float = 5.0,
) -> dict[str, Any] | None:
    root = project / ".sdpstudio" / "runtime" / "event-logs"
    if not root.exists():
        return None
    artifact_root = project / ".sdpstudio" / "runtime" / "run-artifacts" / run_id
    offset_path = artifact_root / "event-log-offsets.json"
    try:
        offsets = (
            json.loads(offset_path.read_text(encoding="utf-8")) if offset_path.exists() else {}
        )
    except (OSError, ValueError, TypeError):
        offsets = {}
    next_offsets: dict[str, int] = {}
    files = [p for p in root.rglob("*") if p.is_file() and p.stat().st_mtime >= started_epoch - 5]
    event_count = 0

    def iter_events() -> Any:
        nonlocal event_count
        for file in sorted(files, key=lambda p: p.stat().st_mtime):
            try:
                if file.stat().st_size > 200 * 1024 * 1024:
                    continue
                with file.open("r", encoding="utf-8", errors="replace") as handle:
                    relative_name = str(file.relative_to(root))
                    start_offset = int(offsets.get(relative_name, 0) or 0)
                    if start_offset > file.stat().st_size:
                        start_offset = 0
                    handle.seek(start_offset)
                    for line in handle:
                        if event_count >= 100_000:
                            break
                        line = line.strip()
                        if not line.startswith("{"):
                            continue
                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(item, dict):
                            event_count += 1
                            yield item
                    next_offsets[relative_name] = handle.tell()
            except OSError:
                continue

    summary = summarize_spark_event_stream(
        iter_events(),
        moderate_skew_ratio=moderate_skew_ratio,
        severe_skew_ratio=severe_skew_ratio,
    )
    if event_count == 0:
        return None
    if next_offsets:
        artifact_root.mkdir(parents=True, exist_ok=True)
        offset_path.write_text(
            json.dumps(next_offsets, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    summary["source_files"] = [str(f.relative_to(project)) for f in files]
    summary["event_count"] = event_count
    target = artifact_root / "event-summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    raw_dir = target.parent / "event-logs"
    raw_files: list[str] = []
    for source in files:
        try:
            relative = source.relative_to(root)
            destination = raw_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            raw_files.append(destination.relative_to(target.parent).as_posix())
        except (OSError, ValueError):
            continue
    summary["raw_artifacts"] = raw_files
    target.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def _ingest_plan_artifacts(project: Path, run_id: str) -> dict[str, Any] | None:
    """Normalize generated per-node Spark explain output into one run artifact."""
    source = project / ".sdpstudio" / "runtime" / "run-artifacts" / run_id / "plans"
    if not source.exists():
        return None
    plans: list[dict[str, Any]] = []
    for path in sorted(source.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw = payload.get("raw")
            node_id = payload.get("node_id")
            if isinstance(raw, str) and isinstance(node_id, str):
                parsed = parse_explain_plan(raw)
                plans.append({"node_id": node_id, "raw": raw, "parsed": parsed})
        except (OSError, ValueError, TypeError):
            continue
    if not plans:
        return None
    artifact = {"run_id": run_id, "source": "spark_dataframe_explain", "plans": plans}
    target = source.parent / "plan.json"
    target.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


async def run_command(
    args: list[str],
    cwd: Path,
    on_line,
    timeout: float | None = None,
    extra_env: dict[str, str] | None = None,
    max_output_bytes: int = 8 * 1024 * 1024,
) -> int:
    if max_output_bytes < 1:
        raise ValueError("max_output_bytes must be positive")
    result = await run_process(
        args,
        cwd=str(cwd),
        timeout=timeout,
        extra_env=extra_env,
        max_output_bytes=max_output_bytes,
        on_line=on_line,
    )
    if result.timed_out:
        raise TimeoutError("process exceeded its timeout")
    return result.returncode


class LocalRuntime:
    def __init__(self, store: Any):
        self.store = store
        self.processes: dict[str, asyncio.subprocess.Process] = {}
        self.tasks: dict[str, asyncio.Task[Any]] = {}

    def reconcile_orphaned_processes(self) -> list[str]:
        """Terminate and account for process records left by a prior server instance."""
        recovered: list[str] = []
        for project in self.store.list_projects():
            root = Path(project["path"]) / ".sdpstudio" / "runtime" / "run-artifacts"
            for marker in root.glob("*/process.json"):
                try:
                    payload = json.loads(marker.read_text(encoding="utf-8"))
                    run_id = str(payload["run_id"])
                    pid = int(payload["pid"])
                except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                    marker.unlink(missing_ok=True)
                    continue
                if pid != os.getpid():
                    with suppress(OSError, ProcessLookupError):
                        os.kill(pid, 15)
                try:
                    run = self.store.get_run(run_id)
                    if run["status"] not in {
                        "succeeded",
                        "validation_failed",
                        "failed",
                        "cancelled",
                        "lost",
                    }:
                        self.store.transition_run(
                            run_id, "lost", error="Process orphaned after server restart"
                        )
                    recovered.append(run_id)
                except KeyError:
                    pass
                marker.unlink(missing_ok=True)
        return recovered

    async def preview(
        self,
        project_id: str,
        node_id: str,
        limit: int = 50,
        profile: dict[str, Any] | None = None,
        include_plan: bool = False,
        include_trace: bool = False,
        include_profile: bool = False,
        sampling_fraction: float = 1.0,
        seed: int = 0,
        timeout_seconds: int = 120,
        cache_ttl_seconds: int = 300,
        force_refresh: bool = False,
        confirm_sink_test: bool = False,
        profile_max_rows: int = 200,
        profile_max_columns: int = 100,
        profile_top_values: int = 5,
    ) -> dict[str, Any]:
        profile = profile or {"adapter": "local", "config": {}}
        adapter = str(profile.get("adapter", "local"))
        if adapter == "kubernetes":
            return {
                "ok": False,
                "problems": [
                    Problem(
                        code="SDPS-PREVIEW-010",
                        severity="error",
                        message="Interactive data preview is not enabled for the Kubernetes submission adapter",
                        remediation="Use Local Spark or Spark Connect for interactive preview; Kubernetes remains available for pipeline runs.",
                    ).model_dump()
                ],
            }
        if not importlib.util.find_spec("pyspark"):
            return {
                "ok": False,
                "problems": [
                    Problem(
                        code="SDPS-PREVIEW-011",
                        severity="error",
                        message="PySpark is not installed in the SDP Studio server environment",
                        remediation="Install SDP Studio with the pipelines extra to enable local/remote Spark previews.",
                    ).model_dump()
                ],
            }
        if adapter == "local" and not shutil.which("java"):
            return {
                "ok": False,
                "problems": [
                    Problem(
                        code="SDPS-PREVIEW-012",
                        severity="error",
                        message="Java is required for local Spark data preview",
                    ).model_dump()
                ],
            }

        remote: str | None = None
        if adapter in {"spark-connect", "databricks-connect"}:
            from .profiles import _resolved_remote

            remote = _resolved_remote(profile.get("config") or {})
            if not remote:
                return {
                    "ok": False,
                    "problems": [
                        Problem(
                            code="SDPS-PREVIEW-013",
                            severity="error",
                            message="Spark Connect remote is not configured for this runtime profile",
                        ).model_dump()
                    ],
                }
        elif adapter != "local":
            return {
                "ok": False,
                "problems": [
                    Problem(
                        code="SDPS-PREVIEW-014",
                        severity="error",
                        message=f"Preview is unsupported for runtime adapter {adapter!r}",
                    ).model_dump()
                ],
            }

        document = self.store.load_pipeline(project_id)
        cache_key = hashlib.sha256(
            json.dumps(
                {
                    "pipeline": document.model_dump(mode="json"),
                    "node_id": node_id,
                    "limit": limit,
                    "profile": profile,
                    "include_plan": include_plan,
                    "include_profile": include_profile,
                    "sampling_fraction": sampling_fraction,
                    "seed": seed,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        cache_dir = self.store.project_path(project_id) / ".sdpstudio" / "runtime" / "preview-cache"
        cache_path = cache_dir / f"{cache_key}.json"
        if not force_refresh and cache_ttl_seconds > 0 and cache_path.exists():
            age = max(0.0, datetime.now(UTC).timestamp() - cache_path.stat().st_mtime)
            if age <= cache_ttl_seconds:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                cached["cache"] = {
                    "hit": True,
                    "age_seconds": round(age, 3),
                    "ttl_seconds": cache_ttl_seconds,
                }
                return cached
        script, problems = generate_preview_script(
            document,
            node_id,
            limit=limit,
            remote_from_env=bool(remote),
            include_plan=include_plan,
            include_trace=include_trace,
            confirm_sink_test=confirm_sink_test,
            include_profile=include_profile,
            sampling_fraction=sampling_fraction,
            seed=seed,
            profile_max_rows=profile_max_rows,
            profile_max_columns=profile_max_columns,
            profile_top_values=profile_top_values,
        )
        if not script:
            return {"ok": False, "problems": [p.model_dump() for p in problems]}

        project = self.store.project_path(project_id)
        preview_dir = project / ".sdpstudio" / "runtime" / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_id = new_ulid()
        script_path = preview_dir / f"{preview_id}.py"
        script_path.write_text(script, encoding="utf-8")
        lines: list[str] = []

        async def collect(line: str) -> None:
            lines.append(line)

        extra_env = {"SDPSTUDIO_PREVIEW_REMOTE": remote} if remote else None
        try:
            code = await run_command(
                [sys.executable, str(script_path)],
                project,
                collect,
                timeout=timeout_seconds,
                extra_env=extra_env,
            )
        except TimeoutError:
            return {
                "ok": False,
                "problems": [
                    Problem(
                        code="SDPS-PREVIEW-015",
                        severity="error",
                        message=f"Preview exceeded the {timeout_seconds} second safety timeout",
                        remediation="Preview a narrower upstream node or optimize the source/filter.",
                    ).model_dump()
                ],
            }
        finally:
            script_path.unlink(missing_ok=True)

        begin = next(
            (i for i, line in enumerate(lines) if line.strip() == "__SDPSTUDIO_PREVIEW_BEGIN__"),
            None,
        )
        end = next(
            (i for i, line in enumerate(lines) if line.strip() == "__SDPSTUDIO_PREVIEW_END__"), None
        )
        if code != 0 or begin is None or end is None or end <= begin + 1:
            return {
                "ok": False,
                "exit_code": code,
                "output": "\n".join(lines[-500:]),
                "problems": [
                    Problem(
                        code="SDPS-PREVIEW-016",
                        severity="error",
                        message="Spark preview failed; inspect the captured output for the source/runtime error",
                    ).model_dump()
                ],
            }
        try:
            payload = json.loads(lines[begin + 1])
        except json.JSONDecodeError:
            return {
                "ok": False,
                "exit_code": code,
                "output": "\n".join(lines[-500:]),
                "problems": [
                    Problem(
                        code="SDPS-PREVIEW-017",
                        severity="error",
                        message="Spark preview returned an unreadable payload",
                    ).model_dump()
                ],
            }
        preview_artifact_dir = project / ".sdpstudio" / "runtime" / "preview-artifacts" / preview_id
        preview_artifact_dir.mkdir(parents=True, exist_ok=True)
        schema_artifact = preview_artifact_dir / "schema.json"
        schema_artifact.write_text(
            json.dumps(
                {"preview_id": preview_id, "node_id": node_id, "schema": payload.get("schema", {})},
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        schema_artifact_ref = str(schema_artifact.relative_to(project)).replace("\\", "/")
        plan_artifact: str | None = None
        if include_plan and isinstance(payload.get("plan"), str):
            parsed_plan = parse_explain_plan(payload["plan"])
            payload["plan_parsed"] = parsed_plan
            plan_path = preview_artifact_dir / "plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "preview_id": preview_id,
                        "node_id": node_id,
                        "runtime_adapter": adapter,
                        "raw": payload["plan"],
                        "parsed": parsed_plan,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            plan_artifact = str(plan_path.relative_to(project)).replace("\\", "/")
        payload.update(
            {
                "ok": True,
                "exit_code": code,
                "runtime_adapter": adapter,
                "output": "\n".join(lines[:begin] + lines[end + 1 :])[-20000:],
            }
        )
        if plan_artifact:
            payload["plan_artifact"] = plan_artifact
        payload["schema_artifact"] = schema_artifact_ref
        if cache_ttl_seconds > 0:
            cache_dir.mkdir(parents=True, exist_ok=True)
            payload["cache"] = {"hit": False, "age_seconds": 0, "ttl_seconds": cache_ttl_seconds}
            cache_path.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
            )
        return payload

    async def dry_run(
        self, project_id: str, profile: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        profile = profile or {"adapter": "local", "config": {}}
        from .profiles import build_run_command, probe_profile

        capabilities = probe_profile(profile)
        if not capabilities.available:
            return {
                "ok": False,
                "problems": [
                    Problem(
                        code="SDPS-RUNTIME-001",
                        severity="error",
                        message=f"Runtime profile {profile.get('adapter', 'local')!r} is not available",
                        remediation="Check this runtime profile and its prerequisites. For local execution install Apache Spark/PySpark 4.2 with the pipelines extra.",
                        details=capabilities.details,
                    ).model_dump()
                ],
            }
        project = self.store.project_path(project_id)
        lines: list[str] = []

        async def collect(line: str) -> None:
            lines.append(line)

        command, _safe, temp_spec = build_run_command(
            profile, project=project, run_id=f"dry-{new_ulid()}", mode="incremental", selected=[]
        )
        command[1] = "dry-run"
        try:
            code = await run_command(command, project, collect, timeout=300)
        finally:
            if temp_spec:
                temp_spec.unlink(missing_ok=True)
        return {"ok": code == 0, "exit_code": code, "output": "\n".join(lines)}

    def submit(
        self,
        project_id: str,
        mode: str = "incremental",
        selected: list[str] | None = None,
        profile: dict[str, Any] | None = None,
        *,
        defer_execution: bool = False,
    ) -> RunRecord:
        selected = selected or []
        profile = profile or {"adapter": "local", "config": {}}
        from sdpstudio_runners.adapters import adapter_for

        try:
            runtime_adapter = adapter_for(profile)
            capabilities = runtime_adapter.probe(profile).capabilities
        except Exception as exc:
            runtime_adapter = None
            capabilities = RuntimeCapabilities(
                adapter=str(profile.get("adapter", "local")),
                available=False,
                details={"error": redact(str(exc))},
            )

        pipeline_document = self.store.load_pipeline(project_id)
        from sdpstudio_server.git_service import run_context

        provenance = run_context(self.store.project_path(project_id))
        graph_payload = json.dumps(
            pipeline_document.model_dump(by_alias=True), sort_keys=True, separators=(",", ":")
        )
        graph_hash = hashlib.sha256(graph_payload.encode("utf-8")).hexdigest()
        run = RunRecord(
            id=new_ulid(),
            project_id=project_id,
            pipeline_id=pipeline_document.pipelineId,
            runtime_profile_id=profile.get("id"),
            mode=mode,
            selected=selected,
            code_hash=self.store.code_hash(project_id),
            source_hash=self.store.code_hash(project_id),
            graph_revision_hash=graph_hash,
            git_commit=provenance["git_commit"],
            git_dirty=provenance["git_dirty"],
            dirty_patch_hash=provenance["dirty_patch_hash"],
        )
        self.store.create_run(run)
        self.store.transition_run(run.id, "queued")
        if profile.get("adapter") == "databricks":
            if defer_execution:
                return RunRecord.model_validate({**run.model_dump(), "status": "queued"})
            self.store.transition_run(run.id, "preparing")
            self.store.transition_run(run.id, "validating")
            self.tasks[run.id] = asyncio.create_task(
                self.execute_managed_databricks(run.id, project_id, profile, mode, selected)
            )
            return RunRecord.model_validate({**run.model_dump(), "status": "submitting"})
        if not defer_execution:
            self.store.transition_run(run.id, "preparing")
            self.store.transition_run(run.id, "validating")
        artifact_dir = (
            self.store.project_path(project_id)
            / ".sdpstudio"
            / "runtime"
            / "run-artifacts"
            / run.id
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        event_log_dir = (
            self.store.project_path(project_id) / ".sdpstudio" / "runtime" / "event-logs" / run.id
        ).resolve()
        snapshot = {
            "run_id": run.id,
            "project_id": project_id,
            "code_hash": run.code_hash,
            "pipeline": pipeline_document.model_dump(by_alias=True),
            "generated_code": self.store.generated_code(project_id),
            "runtime_capabilities": capabilities.model_dump(),
            "runtime_profile": _safe_runtime_profile(profile),
            "git": provenance,
            "spark_event_log": {
                "enabled": profile.get("adapter", "local") == "local",
                "directory": event_log_dir.as_uri()
                if profile.get("adapter", "local") == "local"
                else None,
            },
        }
        (artifact_dir / "run-snapshot.json").write_text(
            json.dumps(snapshot, indent=2, default=str) + "\n", encoding="utf-8"
        )
        if not capabilities.available:
            message = f"Runtime profile {profile.get('adapter', 'local')!r} is unavailable. Check its configuration and Spark SDP prerequisites."
            self.store.transition_run(
                run.id, "failed", finished_at=datetime.now(UTC), error=message
            )
            self.store.add_run_event(run.id, "problem", message, capabilities.model_dump())
            return RunRecord.model_validate(
                {
                    **run.model_dump(),
                    "status": "failed",
                    "finished_at": datetime.now(UTC),
                    "error": message,
                }
            )

        try:
            secret_env = self.store.resolve_secret_references(project_id, profile)
        except Exception as exc:
            message = redact(str(exc))
            self.store.transition_run(
                run.id, "failed", finished_at=datetime.now(UTC), error=message
            )
            self.store.add_run_event(run.id, "problem", message)
            return RunRecord.model_validate(
                {
                    **run.model_dump(),
                    "status": "failed",
                    "finished_at": datetime.now(UTC),
                    "error": message,
                }
            )

        project = self.store.project_path(project_id)
        try:
            if runtime_adapter is None:
                raise RuntimeError(capabilities.details.get("error", "Runtime adapter unavailable"))
            command, safe_command, temp_spec = runtime_adapter.command(
                profile, project=project, run_id=run.id, mode=mode, selected=selected
            )
        except Exception as exc:
            message = redact(str(exc))
            self.store.transition_run(
                run.id, "failed", finished_at=datetime.now(UTC), error=message
            )
            self.store.add_run_event(run.id, "problem", message)
            return RunRecord.model_validate(
                {
                    **run.model_dump(),
                    "status": "failed",
                    "finished_at": datetime.now(UTC),
                    "error": message,
                }
            )
        if defer_execution:
            self.store.update_run(run.id, command_json=safe_command)
            if temp_spec:
                temp_spec.unlink(missing_ok=True)
            return RunRecord.model_validate(
                {**run.model_dump(), "status": "queued", "command": safe_command}
            )
        self.store.transition_run(run.id, "submitting", command_json=safe_command)
        self.tasks[run.id] = asyncio.create_task(
            self._execute(
                run.id,
                project_id,
                command,
                safe_command,
                temp_spec,
                secret_env,
                profile.get("config") or {},
            )
        )
        return RunRecord.model_validate({**run.model_dump(), "command": safe_command})

    async def execute_managed_databricks(
        self,
        run_id: str,
        project_id: str,
        profile: dict[str, Any],
        mode: str,
        selected: list[str],
    ) -> None:
        """Run a managed Databricks update without the local command path."""
        from sdpstudio_runners.adapters import adapter_for

        adapter = adapter_for(profile)
        project = self.store.project_path(project_id)
        try:
            self.store.transition_run(run_id, "submitting")
            validation = await adapter.validate(profile, project)
            if not validation.valid:
                self.store.transition_run(
                    run_id,
                    "validation_failed",
                    finished_at=datetime.now(UTC),
                    error="Databricks validation failed",
                )
                for problem in validation.problems:
                    self.store.add_run_event(
                        run_id, "problem", str(problem.get("message", problem))
                    )
                return
            handle = await adapter.submit(profile, project, run_id, mode, selected)
            async for event in adapter.stream_events(handle):
                self.store.add_run_event(run_id, "status", str(event.get("state", "update")), event)
            status = await adapter.status(handle)
            terminal = "succeeded" if status.state in {"completed", "succeeded"} else "failed"
            if terminal == "succeeded":
                self.store.transition_run(run_id, "running")
                self.store.transition_run(run_id, "collecting_artifacts")
            self.store.transition_run(run_id, terminal, finished_at=datetime.now(UTC))
        except Exception as exc:
            self.store.transition_run(
                run_id, "failed", finished_at=datetime.now(UTC), error=redact(str(exc))
            )
            self.store.add_run_event(run_id, "problem", redact(str(exc)))
        finally:
            self.tasks.pop(run_id, None)

    async def _execute(
        self,
        run_id: str,
        project_id: str,
        command: list[str],
        safe_command: list[str] | None = None,
        temp_spec: Path | None = None,
        secret_env: dict[str, str] | None = None,
        runtime_config: dict[str, Any] | None = None,
    ) -> None:
        project = self.store.project_path(project_id)
        started = datetime.now(UTC)
        self.store.transition_run(run_id, "running", started_at=started)
        self.store.add_run_event(
            run_id, "status", "Run started", {"command": safe_command or command}
        )
        try:
            runtime_env = dict(secret_env or {})
            runtime_env["SDPSTUDIO_PLAN_ARTIFACT_DIR"] = str(
                project / ".sdpstudio" / "runtime" / "run-artifacts" / run_id / "plans"
            )
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(project),
                env=_redacted_env(runtime_env),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self.processes[run_id] = process
            process_marker = (
                project / ".sdpstudio" / "runtime" / "run-artifacts" / run_id / "process.json"
            )
            process_marker.write_text(
                json.dumps(
                    {"run_id": run_id, "pid": process.pid, "started_at": started.isoformat()}
                )
                + "\n",
                encoding="utf-8",
            )
            assert process.stdout is not None
            source_map = _load_source_map(project)
            mapped_lines: set[int] = set()
            while True:
                raw = await process.stdout.readline()
                if not raw:
                    break
                text = redact(raw.decode("utf-8", errors="replace").rstrip())
                self.store.add_run_event(run_id, "log", text)
                generated_line = _generated_line_from_log(text)
                if generated_line is not None and generated_line not in mapped_lines:
                    mapping = _node_for_generated_line(source_map, generated_line)
                    if mapping:
                        mapped_lines.add(generated_line)
                        self.store.add_run_event(
                            run_id,
                            "diagnostic",
                            f"Generated-code failure mapped to visual node {mapping.get('node_id')}",
                            {
                                "code": "SDPS-RUN-MAPPED",
                                "node_id": mapping.get("node_id"),
                                "generated_file": mapping.get("file"),
                                "generated_line": generated_line,
                                "source_range": {
                                    "start": mapping.get("start_line"),
                                    "end": mapping.get("end_line"),
                                },
                                "log_line": text,
                            },
                        )
            code = await process.wait()
            finished = datetime.now(UTC)
            status = "succeeded" if code == 0 else "failed"
            self.store.transition_run(
                run_id,
                "collecting_artifacts",
            )
            plan_artifact = _ingest_plan_artifacts(project, run_id)
            # Persist an automatic per-node execution snapshot for every node
            # observed in the graph. Plan-backed nodes retain their parsed plan
            # metadata; nodes without a Spark plan still receive a durable
            # execution marker for run comparison and timeline consumers.
            planned_nodes = {
                str(item.get("node_id")): item
                for item in (plan_artifact or {}).get("plans", [])
                if isinstance(item, dict) and item.get("node_id")
            }
            document = self.store.load_pipeline(project_id)
            for node in document.nodes:
                plan = planned_nodes.get(node.id)
                self.store.save_node_snapshot(
                    run_id,
                    node.id,
                    metrics={
                        "execution_status": status,
                        "plan_captured": plan is not None,
                    },
                    plan_artifact_id=node.id if plan is not None else None,
                )
            self.store.transition_run(
                run_id,
                status,
                finished_at=finished,
                exit_code=int(code),
                error=None if code == 0 else f"spark-pipelines exited with {code}",
            )
            self.store.add_run_event(run_id, "status", f"Run {status}", {"exit_code": code})
            runtime_config = runtime_config or {}
            summary = _ingest_recent_event_logs(
                project,
                started.timestamp(),
                run_id,
                moderate_skew_ratio=float(runtime_config.get("moderate_skew_ratio", 2.0)),
                severe_skew_ratio=float(runtime_config.get("severe_skew_ratio", 5.0)),
            )
            if summary:
                severe = [
                    stage
                    for stage in summary.get("stages", [])
                    if stage.get("diagnostic") == "severe skew"
                ]
                self.store.add_run_event(
                    run_id,
                    "debug",
                    f"Spark event log analyzed: {len(summary.get('stages', []))} stage(s), {len(severe)} severe skew warning(s)",
                    summary,
                )
            if plan_artifact:
                self.store.add_run_event(
                    run_id,
                    "debug",
                    f"Captured Spark plans for {len(plan_artifact['plans'])} node(s)",
                    {
                        "artifact": f".sdpstudio/runtime/run-artifacts/{run_id}/plan.json",
                        "source": "spark_dataframe_explain",
                        "node_count": len(plan_artifact["plans"]),
                    },
                )
        except asyncio.CancelledError:
            self.store.transition_run(run_id, "cancelled", finished_at=datetime.now(UTC))
            self.store.add_run_event(run_id, "status", "Run cancelled")
            raise
        except Exception as exc:
            self.store.transition_run(
                run_id, "failed", finished_at=datetime.now(UTC), error=redact(str(exc))
            )
            self.store.add_run_event(run_id, "problem", redact(str(exc)))
        finally:
            if temp_spec:
                temp_spec.unlink(missing_ok=True)
            self.processes.pop(run_id, None)
            process_marker = (
                project / ".sdpstudio" / "runtime" / "run-artifacts" / run_id / "process.json"
            )
            process_marker.unlink(missing_ok=True)
            self.tasks.pop(run_id, None)

    async def cancel(self, run_id: str) -> bool:
        remote_cancelled = await self._cancel_kubernetes_driver(run_id)
        process = self.processes.get(run_id)
        if not process or process.returncode is not None:
            return remote_cancelled
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except TimeoutError:
            process.kill()
            await process.wait()
        return True

    def _kubernetes_lifecycle(self, run_id: str):
        from sdpstudio_runners.adapters import KubernetesLifecycle

        run = self.store.get_run(run_id)
        project = self.store.project_path(run["project_id"])
        snapshot = (
            project / ".sdpstudio" / "runtime" / "run-artifacts" / run_id / "run-snapshot.json"
        )
        if not snapshot.exists():
            return None
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        profile = payload.get("runtime_profile") or {}
        if profile.get("adapter") != "kubernetes":
            return None
        config = profile.get("config") or {}
        namespace = str(config.get("namespace") or "default")
        driver_name = str(config.get("driver_name") or f"sdpstudio-{run_id.lower()}-driver")
        kubectl = str(config.get("kubectl") or "kubectl")
        return KubernetesLifecycle(namespace, driver_name, kubectl)

    async def _kubectl(self, command: list[str], *, timeout: float = 20.0) -> dict[str, Any]:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            output = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            return {"ok": False, "output": "kubectl request timed out"}
        text = redact(output[0].decode("utf-8", errors="replace"))
        return {"ok": process.returncode == 0, "output": text, "exit_code": process.returncode}

    async def kubernetes_status(self, run_id: str) -> dict[str, Any]:
        lifecycle = self._kubernetes_lifecycle(run_id)
        if lifecycle is None:
            return {
                "ok": False,
                "supported": False,
                "message": "Run is not a Kubernetes submission",
            }
        command, safe = lifecycle.status_command()
        result = await self._kubectl(command)
        result.update({"supported": True, "command": safe, "run_id": run_id})
        if result.get("ok"):
            try:
                result["pod"] = json.loads(result["output"])
                pod = result["pod"]
                phase = str((pod.get("status") or {}).get("phase", "")).lower()
                result["lifecycle_status"] = phase or "unknown"
                if phase == "succeeded":
                    current = self.store.get_run(run_id)["status"]
                    if current not in {
                        "succeeded",
                        "failed",
                        "cancelled",
                        "validation_failed",
                        "lost",
                    }:
                        if current == "running":
                            self.store.transition_run(run_id, "collecting_artifacts")
                        self.store.transition_run(
                            run_id, "succeeded", finished_at=datetime.now(UTC), exit_code=0
                        )
                elif phase in {"failed", "error"}:
                    current = self.store.get_run(run_id)["status"]
                    if current not in {
                        "succeeded",
                        "failed",
                        "cancelled",
                        "validation_failed",
                        "lost",
                    }:
                        self.store.transition_run(
                            run_id,
                            "failed",
                            finished_at=datetime.now(UTC),
                            exit_code=1,
                            error=f"Kubernetes driver pod entered {phase} state",
                        )
            except (TypeError, ValueError):
                result["ok"] = False
                result["message"] = "kubectl returned invalid pod JSON"
        executor_command, executor_safe = lifecycle.executor_pods_command()
        executor_result = await self._kubectl(executor_command)
        result["executor_command"] = executor_safe
        if executor_result.get("ok"):
            try:
                executor_payload = json.loads(executor_result["output"])
                result["executors"] = (
                    executor_payload.get("items", []) if isinstance(executor_payload, dict) else []
                )
            except (TypeError, ValueError):
                result["executors"] = []
                result["executor_error"] = "kubectl returned invalid executor pod JSON"
        else:
            result["executors"] = []
            result["executor_error"] = executor_result.get("output", "executor query failed")
        return result

    async def kubernetes_probe(self, run_id: str) -> dict[str, Any]:
        """Check Kubernetes connectivity and the minimum pod-read permission."""
        lifecycle = self._kubernetes_lifecycle(run_id)
        if lifecycle is None:
            return {
                "ok": False,
                "supported": False,
                "message": "Run is not a Kubernetes submission",
            }
        checks: dict[str, bool] = {}
        for name, command, _safe in lifecycle.access_check_commands():
            probe = await self._kubectl(command)
            checks[name] = bool(
                probe.get("ok") and probe.get("output", "").strip().lower() == "yes"
            )
        command, safe = lifecycle.access_check_command()
        result = {
            "ok": all(checks.values()),
            "output": "yes" if all(checks.values()) else "no",
            "exit_code": 0,
            "permissions": checks,
        }
        allowed = bool(result["ok"])
        result.update(
            {
                "ok": bool(allowed),
                "supported": True,
                "authorized": bool(allowed),
                "command": safe,
                "run_id": run_id,
            }
        )
        if not allowed and "message" not in result:
            result["message"] = "kubectl cannot read pods in the configured namespace"
        return result

    async def kubernetes_logs(
        self, run_id: str, *, tail: int = 200, follow: bool = False
    ) -> dict[str, Any]:
        lifecycle = self._kubernetes_lifecycle(run_id)
        if lifecycle is None:
            return {
                "ok": False,
                "supported": False,
                "message": "Run is not a Kubernetes submission",
            }
        command, safe = lifecycle.logs_command(tail=tail, follow=follow)
        result = await self._kubectl(command, timeout=120 if follow else 20)
        result.update({"supported": True, "command": safe, "run_id": run_id})
        return result

    async def kubernetes_events(self, run_id: str) -> dict[str, Any]:
        lifecycle = self._kubernetes_lifecycle(run_id)
        if lifecycle is None:
            return {
                "ok": False,
                "supported": False,
                "message": "Run is not a Kubernetes submission",
            }
        command, safe = lifecycle.events_command()
        result = await self._kubectl(command)
        result.update({"supported": True, "command": safe, "run_id": run_id})
        if result.get("ok"):
            try:
                payload = json.loads(result["output"])
                result["events"] = payload.get("items", []) if isinstance(payload, dict) else []
                self.store.add_run_event(
                    run_id,
                    "runtime",
                    "Kubernetes driver events collected",
                    {"count": len(result["events"])},
                )
            except (TypeError, ValueError):
                result["ok"] = False
                result["message"] = "kubectl returned invalid event JSON"
        return result

    async def _cancel_kubernetes_driver(self, run_id: str) -> bool:
        lifecycle = self._kubernetes_lifecycle(run_id)
        if lifecycle is None:
            return False
        command, _safe = lifecycle.cancel_command()
        result = await self._kubectl(command)
        if result.get("ok"):
            self.store.transition_run(run_id, "cancelled", finished_at=datetime.now(UTC))
            self.store.add_run_event(run_id, "status", "Kubernetes driver cancelled")
        return bool(result.get("ok"))
