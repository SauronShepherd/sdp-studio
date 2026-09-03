from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from .collaboration_merge import server_merge_available

COLLABORATION_CAPABILITIES = {
    "transport": "websocket",
    "document_format": "yjs-update-bundle",
    "durable_updates": True,
    "offline_recovery": True,
    "presence": True,
    "server_merge": server_merge_available(),
    "merge_model": "server-side-y-crdt-when-collaboration-extra-is-installed",
}


class CollaborationHub:
    """In-process project presence and delivery for durable collaboration updates.

    Presence and WebSocket connections are intentionally ephemeral. Yjs update
    events are persisted by ``DataStore`` and replayed from the durable snapshot
    and event log when a client reconnects.
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._presence: dict[str, dict[WebSocket, dict[str, Any]]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    @staticmethod
    def _remote_collaborators(connection_count: int) -> int:
        """Translate total sockets into peers visible to the current client."""

        return max(0, connection_count - 1)

    async def connect(self, project_id: str, ws: WebSocket) -> int:
        async with self._lock:
            self._connections[project_id].add(ws)
            self._presence[project_id][ws] = {"selected_node_id": None, "cursor": None}
            return self._remote_collaborators(len(self._connections[project_id]))

    async def disconnect(self, project_id: str, ws: WebSocket) -> int:
        async with self._lock:
            group = self._connections.get(project_id)
            if group:
                group.discard(ws)
                if not group:
                    self._connections.pop(project_id, None)
                    self._presence.pop(project_id, None)
                    return 0
                self._presence.get(project_id, {}).pop(ws, None)
                return self._remote_collaborators(len(group))
            return 0

    async def update_presence(
        self, project_id: str, ws: WebSocket, payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        async with self._lock:
            if ws not in self._connections.get(project_id, set()):
                return []
            current = self._presence.setdefault(project_id, {}).setdefault(ws, {})
            current["selected_node_id"] = (
                payload.get("selected_node_id")
                if isinstance(payload.get("selected_node_id"), str)
                else None
            )
            cursor = payload.get("cursor")
            current["cursor"] = cursor if isinstance(cursor, dict) else None
            return [dict(item) for self_ws, item in self._presence.get(project_id, {}).items() if self_ws is not ws]

    async def broadcast(self, project_id: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections.get(project_id, ()))
        stale: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                stale.append(ws)
        if stale:
            async with self._lock:
                group = self._connections.get(project_id)
                if group:
                    for ws in stale:
                        group.discard(ws)

    async def presence(self, project_id: str) -> int:
        """Return total live sockets for server-side health/diagnostic callers."""

        async with self._lock:
            return len(self._connections.get(project_id, ()))
