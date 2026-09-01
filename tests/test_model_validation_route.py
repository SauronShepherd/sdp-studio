from fastapi.testclient import TestClient
from sdpstudio_server.app import create_app


def test_validate_model_normative_alias(tmp_path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "model"}).json()
    response = client.post(f"/api/projects/{project['id']}/validate-model")
    assert response.status_code == 200
    assert {"valid", "problems"} <= response.json().keys()
