from fastapi.testclient import TestClient
from sdpstudio_server.app import create_app


def _receive_presence(socket, expected_count: int) -> None:
    for _ in range(6):
        message = socket.receive_json()
        if message.get("type") == "presence":
            assert message["count"] == expected_count
            return
    raise AssertionError(f"presence count {expected_count} was not received")


def test_normative_websocket_paths_are_registered(tmp_path):
    app = create_app(tmp_path)
    websocket_paths = {route.path for route in app.routes if route.path.startswith("/ws/")}
    assert "/ws/projects/{project_id}" in websocket_paths
    assert "/ws/collab/{project_id}" in websocket_paths
    assert "/ws/runs/{run_id}" in websocket_paths


def test_project_websocket_broadcasts_presence_lifecycle(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        project = client.post("/api/projects", json={"name": "presence-lifecycle"}).json()
        project_id = project["id"]

        with client.websocket_connect(
            f"/ws/projects/{project_id}", subprotocols=["sdpstudio.v1"]
        ) as first:
            _receive_presence(first, 1)

            with client.websocket_connect(
                f"/ws/projects/{project_id}", subprotocols=["sdpstudio.v1"]
            ) as second:
                _receive_presence(first, 2)
                _receive_presence(second, 2)

            _receive_presence(first, 1)
