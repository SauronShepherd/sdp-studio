"""Durable run-lease worker primitives.

Execution is injected so adapters remain responsible for provider-specific
submission while this module owns claiming, lease renewal, and failure release.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from .storage import DataStore


class DurableRunWorker:
    def __init__(self, store: DataStore, worker_id: str, executor: Callable[[dict[str, Any]], Any]):
        self.store = store
        self.worker_id = worker_id
        self.executor = executor

    def poll_once(self, lease_seconds: int = 60) -> dict[str, Any] | None:
        """Claim and execute at most one run; return the claimed record."""
        claimed = self.store.claim_run(self.worker_id, lease_seconds=lease_seconds)
        if claimed is None:
            return None
        token = str(claimed["claim_token"])
        try:
            self.executor(claimed)
        except Exception:
            self.store.release_run_claim(str(claimed["id"]), token)
            raise
        return claimed

    def heartbeat(self, run_id: str, claim_token: str) -> bool:
        return self.store.heartbeat_run(run_id, claim_token)

    async def poll_once_async(
        self,
        lease_seconds: int = 60,
        executor: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any] | None:
        """Claim and execute one run, supporting async runtime adapters.

        The claim is released only after the executor completes.  A failed
        executor releases the lease so another worker can retry it; a
        successfully completed executor also releases it, preventing stale
        ownership from blocking subsequent recovery.
        """
        claimed = self.store.claim_run(self.worker_id, lease_seconds=lease_seconds)
        if claimed is None:
            return None
        token = str(claimed["claim_token"])
        operation = executor or self.executor
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(str(claimed["id"]), token, lease_seconds)
        )
        try:
            result = operation(claimed)
            if inspect.isawaitable(result):
                await result
        except Exception:
            self.store.release_run_claim(str(claimed["id"]), token)
            raise
        finally:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
        self.store.release_run_claim(str(claimed["id"]), token)
        return claimed

    async def _heartbeat_loop(self, run_id: str, claim_token: str, lease_seconds: int) -> None:
        interval = max(0.1, min(30.0, max(1, lease_seconds) / 3))
        while True:
            await asyncio.sleep(interval)
            if not self.heartbeat(run_id, claim_token):
                return

    async def drain_async(
        self,
        *,
        lease_seconds: int = 60,
        executor: Callable[[dict[str, Any]], Any] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Process available queued work until the queue is empty or bounded."""
        completed: list[dict[str, Any]] = []
        while limit is None or len(completed) < limit:
            item = await self.poll_once_async(lease_seconds, executor)
            if item is None:
                break
            completed.append(item)
            # A successful executor normally advances the run out of queued
            # state.  Stop defensively when an injected test/executor leaves
            # it queued, otherwise releasing the lease would make the same
            # record immediately claimable again.
            if self.store.get_run(str(item["id"]))["status"] == "queued":
                break
        return completed


async def execute_queued_local_run(store: DataStore, record: dict[str, Any]) -> None:
    """Execute one claimed local run from only persisted run metadata.

    This is the process boundary used by the standalone worker.  Runtime
    profile, mode, selected nodes, and project ownership are reconstructed
    from the database; no web-server task or in-memory submission state is
    required.
    """
    from sdpstudio_runners.adapters import adapter_for
    from sdpstudio_runners.local import LocalRuntime

    run_id = str(record["id"])
    project_id = str(record["project_id"])
    runtime_profile = (
        store.get_runtime_profile(str(record["runtime_profile_id"]))
        if record.get("runtime_profile_id")
        else {"adapter": "local", "config": {}}
    )
    selected = json.loads(str(record.get("selected_json") or "[]"))
    mode = str(record.get("mode") or "incremental")
    adapter = adapter_for(runtime_profile)
    project = store.project_path(project_id)
    (project / ".sdpstudio" / "runtime" / "run-artifacts" / run_id).mkdir(
        parents=True, exist_ok=True
    )
    (project / ".sdpstudio" / "runtime" / "event-logs" / run_id).mkdir(parents=True, exist_ok=True)
    if runtime_profile.get("adapter") == "databricks":
        runtime = LocalRuntime(store)
        store.transition_run(run_id, "preparing")
        store.transition_run(run_id, "validating")
        await runtime.execute_managed_databricks(
            run_id, project_id, runtime_profile, mode, selected
        )
        return
    command, safe_command, temp_spec = adapter.command(
        runtime_profile,
        project=project,
        run_id=run_id,
        mode=mode,
        selected=selected,
    )
    try:
        store.transition_run(run_id, "preparing")
        store.transition_run(run_id, "validating")
        store.transition_run(run_id, "submitting", command_json=safe_command)
        secret_env = store.resolve_secret_references(project_id, runtime_profile)
        runtime = LocalRuntime(store)
        runtime_config = runtime_profile.get("config")
        if not isinstance(runtime_config, dict):
            runtime_config = {}
        await runtime._execute(
            run_id,
            project_id,
            command,
            safe_command,
            temp_spec,
            secret_env,
            runtime_config,
        )
    except Exception as exc:
        if store.get_run(run_id)["status"] not in {
            "succeeded",
            "failed",
            "cancelled",
            "validation_failed",
            "lost",
        }:
            store.transition_run(run_id, "failed", error=str(exc))
        raise
    finally:
        if temp_spec:
            temp_spec.unlink(missing_ok=True)
