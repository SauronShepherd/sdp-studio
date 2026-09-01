"""Async server boundary for runtime execution."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any


class RuntimeDispatch:
    """Awaitable boundary that keeps blocking runtime setup off the event loop.

    Adapter-backed runs retain the exact adapter instance that submitted them.
    This is required for factory-created remote adapters where cancellation,
    status, event streaming, and artifact collection must be routed back to
    the same provider/session rather than falling through to the local runtime.
    """

    def __init__(
        self, implementation: Any, adapter: Any | None = None, adapter_factory: Any | None = None
    ) -> None:
        self._implementation = implementation
        self._adapter = adapter
        self._adapter_factory = adapter_factory
        self._handles: dict[str, tuple[Any, Any]] = {}

    def _resolve_adapter(self, profile: dict[str, Any]) -> Any | None:
        adapter = self._adapter
        if self._adapter_factory is not None and profile.get("adapter") not in {None, "local"}:
            adapter = self._adapter_factory(profile)
        return adapter

    async def submit(self, *args: Any, **kwargs: Any) -> Any:
        # The API queues runs for the durable worker. Persist the canonical
        # record first; direct adapter submission is reserved for callers that
        # explicitly request immediate execution.
        if kwargs.get("defer_execution"):
            return await asyncio.to_thread(self._implementation.submit, *args, **kwargs)
        profile = kwargs.get("profile") or {"adapter": "local", "config": {}}
        adapter = self._resolve_adapter(profile)
        if adapter is not None:
            if not args:
                raise TypeError("project_id is required")
            project_id = str(args[0])
            mode = str(args[1]) if len(args) > 1 else str(kwargs.get("mode", "incremental"))
            selected = list(args[2]) if len(args) > 2 else list(kwargs.get("selected", []))
            project = self._implementation.store.project_path(project_id)
            handle = await adapter.submit(profile, project, "", mode, selected)
            self._handles[handle.id] = (adapter, handle)
            return handle
        return await asyncio.to_thread(self._implementation.submit, *args, **kwargs)

    async def preview(self, project_id: str, node_id: str, limit: int = 50, **kwargs: Any) -> Any:
        """Route preview through the selected async adapter boundary."""
        profile = kwargs.pop("profile", None) or {"adapter": "local", "config": {}}
        adapter = self._resolve_adapter(profile)
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
        adapter = self._resolve_adapter(profile)
        if adapter is None:
            return await asyncio.to_thread(self._implementation.dry_run, project_id, **kwargs)
        project = self._implementation.store.project_path(project_id)
        result = await adapter.validate(profile, project)
        return {"ok": result.valid, "problems": list(result.problems)}

    async def cancel(self, run_id: str) -> bool:
        owned = self._handles.get(run_id)
        if owned is not None:
            adapter, handle = owned
            await adapter.cancel(handle)
            return True
        return await asyncio.to_thread(self._implementation.cancel, run_id)

    async def status(self, run_id: str) -> Any:
        """Return status from the adapter that owns ``run_id`` when applicable."""
        owned = self._handles.get(run_id)
        if owned is not None:
            adapter, handle = owned
            return await adapter.status(handle)
        status = getattr(self._implementation, "status", None)
        if not callable(status):
            raise KeyError(f"Unknown run: {run_id}")
        return await asyncio.to_thread(status, run_id)

    async def stream_events(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        """Stream events through the same adapter/session used for submission."""
        owned = self._handles.get(run_id)
        if owned is not None:
            adapter, handle = owned
            async for event in adapter.stream_events(handle):
                yield event
            return
        stream = getattr(self._implementation, "stream_events", None)
        if not callable(stream):
            raise KeyError(f"Unknown run: {run_id}")
        result = stream(run_id)
        if hasattr(result, "__aiter__"):
            async for event in result:
                yield event
            return
        for event in await asyncio.to_thread(list, result):
            yield event

    async def collect_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        """Collect artifacts through the adapter that owns ``run_id``."""
        owned = self._handles.get(run_id)
        if owned is not None:
            adapter, handle = owned
            return list(await adapter.collect_artifacts(handle))
        collect = getattr(self._implementation, "collect_artifacts", None)
        if not callable(collect):
            return []
        return list(await asyncio.to_thread(collect, run_id))
