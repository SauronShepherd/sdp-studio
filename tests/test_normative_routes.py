from fastapi.testclient import TestClient
from sdpstudio_server.app import create_app


def test_normative_project_tree_and_run_events_routes(tmp_path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "routes"}).json()
    project_id = project["id"]

    tree = client.get(f"/api/projects/{project_id}/tree")
    assert tree.status_code == 200
    assert any(item["path"] == ".sdpstudio/project.yaml" for item in tree.json())

    missing_events = client.get("/api/runs/missing/events")
    assert missing_events.status_code == 404


def test_debug_bundle_supports_normative_post_method(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/runs/missing/debug-bundle")
    assert response.status_code == 404


def test_normative_history_and_review_aliases_are_described(tmp_path):
    client = TestClient(create_app(tmp_path))
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/projects/{project_id}/history/{revision_id}" in paths
    assert "/api/projects/{project_id}/history/{revision_id}/diff" in paths
    assert "/api/projects/{project_id}/history/{revision_id}/restore" in paths
    assert "/api/projects/{project_id}/reviews" in paths
