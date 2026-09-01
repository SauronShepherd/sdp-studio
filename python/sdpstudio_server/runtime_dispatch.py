"""Async server boundary for runtime execution."""

from __future__ import annotations

import asyncio
from typing import Any


class RuntimeDispatch:
    """Awaitable boundary that keeps blocking runtime setup off the event loop."""

    def __init__(
        self, implementation: Any, adapter: Any | None = None, adapter_factory: Any | None = None
    ) -> None:
        self._implementation = implementation
        self._adapter = adapter
        self._adapter_factory = adapter_factory
        self._handles: dict[str, Any] = {}

    async def submit(self, *args: Any, **kwargs: Any) -> Any:
        # The API queues runs for the durable worker. Persist the canonical
        # record first; direct adapter submission is reserved for callers that
        # explicitly request immediate execution.
        if kwargs.get("defer_execution"):
            return await asyncio.to_thread(self._implementation.submit, *args, **kwargs)
        profile = kwargs.get("profile") or {"adapter": "local", "config": {}}
        adapter = self._adapter
        if self._adapter_factory is not None and profile.get("adapter") not in {None, "local"}:
            adapter = self._adapter_factory(profile)
        if adapter is not None:
            if not args:
                raise TypeError("project_id is required")
            project_id = str(args[0])
            mode = str(args[1]) if len(args) > 1 else str(kwargs.get("mode", "incremental"))
            selected = list(args[2]) if len(args) > 2 else list(kwargs.get("selected", []))
            profile = profile
            project = self._implementation.store.project_path(project_id)
            handle = await adapter.submit(profile, project, "", mode, selected)
            self._handles[handle.id] = handle
            return handle
        return await asyncio.to_thread(self._implementation.submit, *args, **kwargs)

    async def preview(self, project_id: str, node_id: str, limit: int = 50, **kwargs: Any) -> Any:
        """Route preview through the selected async adapter boundary."""
        profile = kwargs.pop("profile", None) or {"adapter": "local", "config": {}}
        adapter = self._adapter
        if self._adapter_factory is not None and profile.get("adapter") not in {None, "local"}:
            adapter = self._adapter_factory(profile)
        if adapter is None:
            return await asyncio.to_thread(
                self._implementation.preview, project_id, node_id, limit, **kwargs
            )
        project = self._implementation.store.project_path(project_id)
        result = await adapter.preview(profile, project, node_id, int(limit))
        if isinstance(result, dict):
            return result
        return {
            "ok": True,
            "rows": list(result.rows),
            "schema": {"fields": list(result.schema)},
            "profile": result.metrics,
        }

    async def dry_run(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        """Route validation/dry-run through the selected async adapter boundary."""
        profile = kwargs.pop("profile", None) or {"adapter": "local", "config": {}}
        adapter = self._adapter
        if self._adapter_factory is not None and profile.get("adapter") not in {None, "local"}:
            adapter = self._adapter_factory(profile)
        if adapter is None:
            return await asyncio.to_thread(self._implementation.dry_run, project_id, **kwargs)
        project = self._implementation.store.project_path(project_id)
        result = await adapter.validate(profile, project)
        return {"ok": result.valid, "problems": list(result.problems)}

    async def cancel(self, run_id: str) -> bool:
        if self._adapter is not None:
            handle = self._handles.get(run_id)
            if handle is None:
                return False
            await self._adapter.cancel(handle)
            return True
        return await asyncio.to_thread(self._implementation.cancel, run_id)
