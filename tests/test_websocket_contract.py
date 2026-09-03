from fastapi.testclient import TestClient
from sdpstudio_server.app import create_app


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
            assert first.receive_json() == {"type": "presence", "count": 1}

            with client.websocket_connect(
                f"/ws/projects/{project_id}", subprotocols=["sdpstudio.v1"]
            ) as second:
                assert first.receive_json() == {"type": "presence", "count": 2}
                assert second.receive_json() == {"type": "presence", "count": 2}

            assert first.receive_json() == {"type": "presence", "count": 1}
