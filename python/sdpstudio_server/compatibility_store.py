"""Explicit boundary for operations still backed by the legacy store."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any


class CompatibilityStoreBoundary:
    """Run unmigrated store operations without exposing them to route code."""

    def __init__(self, store: Any) -> None:
        self._store = store

    async def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        operation = getattr(self._store, method)
        return await asyncio.to_thread(partial(operation, *args, **kwargs))

    @property
    def sync_store(self) -> Any:
        """Expose the compatibility store only to lifecycle integrations."""
        return self._store
