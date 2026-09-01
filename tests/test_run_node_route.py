from fastapi.testclient import TestClient
from sdpstudio_core.models import RunRecord
from sdpstudio_server.app import create_app
from sdpstudio_server.storage import DataStore


def test_run_node_detail_returns_persisted_snapshot(tmp_path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "node-detail"}).json()
    store = DataStore(tmp_path)
    run = RunRecord(project_id=project["id"], status="failed")
    store.create_run(run)
    store.save_node_snapshot(
        run.id, "filter", schema=[{"name": "id", "type": "integer"}], profile={"rows": 2}
    )

    response = client.get(f"/api/runs/{run.id}/nodes/filter")
    assert response.status_code == 200
    assert response.json()["node_id"] == "filter"


def test_run_node_detail_returns_not_found_for_unknown_node(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/runs/missing/nodes/filter")
    assert response.status_code == 404
