from pathlib import Path

from fastapi.testclient import TestClient
from sdpstudio_server.app import create_app
from sdpstudio_server.collaboration_merge import server_merge_available


def test_collaboration_capabilities_make_merge_boundary_explicit(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "collab-capabilities"}).json()
    response = client.get(f"/api/projects/{project['id']}/collaboration/capabilities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["durable_updates"] is True
    assert payload["offline_recovery"] is True
    assert payload["server_merge"] is server_merge_available()
