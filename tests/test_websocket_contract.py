import tomllib
from pathlib import Path

from sdpstudio_server.app import create_app


def test_normative_websocket_paths_are_registered(tmp_path):
    app = create_app(tmp_path)
    websocket_paths = {route.path for route in app.routes if route.path.startswith("/ws/")}
    assert "/ws/collab/{project_id}" in websocket_paths
    assert "/ws/runs/{run_id}" in websocket_paths


def test_server_distribution_declares_websocket_protocol_runtime():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert any(dependency.startswith("websockets>=") for dependency in project["dependencies"])
