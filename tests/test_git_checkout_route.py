from fastapi.testclient import TestClient
from sdpstudio_server.app import create_app


def test_git_checkout_route_is_exposed(tmp_path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "checkout"}).json()
    initialized = client.post(f"/api/projects/{project['id']}/git/init")
    assert initialized.status_code == 200
    assert client.post(f"/api/projects/{project['id']}/git/stage").status_code == 200
    assert (
        client.post(
            f"/api/projects/{project['id']}/git/commit", json={"message": "initial"}
        ).status_code
        == 200
    )
    response = client.post(f"/api/projects/{project['id']}/git/checkout", json={"name": "main"})
    assert response.status_code == 200
    history = client.get(f"/api/projects/{project['id']}/history")
    assert history.status_code == 200
    assert any("before git" in str(item.get("reason")) for item in history.json())
