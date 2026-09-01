from fastapi.testclient import TestClient
from sdpstudio_server.app import create_app


def test_global_schedule_list_and_create_routes(tmp_path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "schedules"}).json()
    created = client.post(
        "/api/schedules",
        json={
            "project_id": project["id"],
            "name": "hourly",
            "cron": "0 * * * *",
            "timezone": "UTC",
        },
    )
    assert created.status_code == 200
    listed = client.get("/api/schedules")
    assert listed.status_code == 200
    assert any(item["id"] == created.json()["id"] for item in listed.json())
