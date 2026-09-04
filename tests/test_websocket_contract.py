import asyncio
import tomllib
from pathlib import Path

from sdpstudio_server.app import create_app
from sdpstudio_server.collab import CollaborationHub


def test_normative_websocket_paths_are_registered(tmp_path):
    app = create_app(tmp_path)
    websocket_paths = {route.path for route in app.routes if route.path.startswith("/ws/")}
    assert "/ws/collab/{project_id}" in websocket_paths
    assert "/ws/runs/{run_id}" in websocket_paths


def test_server_distribution_declares_websocket_protocol_runtime():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert any(dependency.startswith("websockets>=") for dependency in project["dependencies"])


def test_presence_counts_remote_collaborators_and_excludes_self_state():
    async def exercise() -> None:
        hub = CollaborationHub()
        first = object()
        second = object()

        assert await hub.connect("project", first) == 0
        assert await hub.connect("project", second) == 1
        assert await hub.presence("project") == 2

        first_peers = await hub.update_presence(
            "project", first, {"selected_node_id": "node-a", "cursor": {"line": 3}}
        )
        assert first_peers == [{"selected_node_id": None, "cursor": None}]

        assert await hub.disconnect("project", second) == 0
        assert await hub.presence("project") == 1

    asyncio.run(exercise())
