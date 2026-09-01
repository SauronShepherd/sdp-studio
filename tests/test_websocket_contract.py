from sdpstudio_server.app import create_app


def test_normative_websocket_paths_are_registered(tmp_path):
    app = create_app(tmp_path)
    websocket_paths = {route.path for route in app.routes if route.path.startswith("/ws/")}
    assert "/ws/collab/{project_id}" in websocket_paths
    assert "/ws/runs/{run_id}" in websocket_paths
