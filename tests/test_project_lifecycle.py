from fastapi.testclient import TestClient
from sdpstudio_server.app import create_app


def test_project_update_and_delete_are_persisted_and_scoped(tmp_path):
    client = TestClient(create_app(tmp_path))
    created = client.post("/api/projects", json={"name": "before"}).json()
    project_id = created["id"]
    project_path = __import__("pathlib").Path(created["path"])
    updated = client.patch(f"/api/projects/{project_id}", json={"name": "after"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "after"
    assert client.get(f"/api/projects/{project_id}").json()["metadata"]["name"] == "after"
    deleted = client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404
    assert project_path.exists()
