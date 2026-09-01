from fastapi.testclient import TestClient
from sdpstudio_core.models import RunRecord
from sdpstudio_server.app import create_app
from sdpstudio_server.storage import DataStore


def test_global_run_compare_resolves_project_and_reuses_comparison_engine(tmp_path):
    app = create_app(tmp_path)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "compare"}).json()
    store = DataStore(tmp_path)
    left = RunRecord(project_id=project["id"], status="failed")
    right = RunRecord(project_id=project["id"], status="failed")
    store.create_run(left)
    store.create_run(right)

    response = client.post(
        "/api/runs/compare",
        json={"left_run_id": left.id, "right_run_id": right.id},
    )
    assert response.status_code == 200
    assert response.json()["left"]["id"] == left.id
    assert response.json()["right"]["id"] == right.id


def test_global_run_compare_rejects_missing_left_run(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/runs/compare",
        json={"left_run_id": "missing", "right_run_id": "missing"},
    )
    assert response.status_code == 404
