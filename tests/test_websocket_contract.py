import asyncio

from sdpstudio_server.app import create_app
from sdpstudio_server.collab import CollaborationHub


class _FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.messages.append(payload)


def test_normative_websocket_paths_are_registered(tmp_path):
    app = create_app(tmp_path)
    websocket_paths = {route.path for route in app.routes if route.path.startswith("/ws/")}
    assert "/ws/projects/{project_id}" in websocket_paths
    assert "/ws/collab/{project_id}" in websocket_paths
    assert "/ws/runs/{run_id}" in websocket_paths


def test_collaboration_hub_broadcasts_presence_lifecycle():
    async def exercise() -> None:
        hub = CollaborationHub()
        first = _FakeWebSocket()
        second = _FakeWebSocket()
        project_id = "presence-lifecycle"

        assert await hub.connect(project_id, first) == 1
        await hub.broadcast(project_id, {"type": "presence", "count": 1})
        assert first.messages[-1] == {"type": "presence", "count": 1}

        assert await hub.connect(project_id, second) == 2
        await hub.broadcast(project_id, {"type": "presence", "count": 2})
        assert first.messages[-1] == {"type": "presence", "count": 2}
        assert second.messages[-1] == {"type": "presence", "count": 2}

        assert await hub.disconnect(project_id, second) == 1
        await hub.broadcast(project_id, {"type": "presence", "count": 1})
        assert first.messages[-1] == {"type": "presence", "count": 1}

    asyncio.run(exercise())
