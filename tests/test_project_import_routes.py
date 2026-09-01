from fastapi.testclient import TestClient
from sdpstudio_server.app import create_app


def test_project_scoped_python_import_alias(tmp_path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "imports"}).json()
    response = client.post(
        f"/api/projects/{project['id']}/import/python",
        json={"path": "generated.py", "source": "from pyspark import pipelines as dp\n"},
    )
    assert response.status_code == 200
    assert "source_sha256" in response.json()


def test_project_scoped_import_rejects_unknown_project(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/projects/missing/import",
        json={"path": "generated.py", "source": "# source"},
    )
    assert response.status_code == 404


def test_project_reconcile_rejects_unsupported_source_without_writing(tmp_path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "reconcile"}).json()
    response = client.post(
        f"/api/projects/{project['id']}/reconcile/python",
        json={"source": "def custom():\n    return custom_udf()\n"},
    )
    assert response.status_code == 200
    assert response.json()["ownership"] == "custom"
    assert response.json()["changed"] is False
