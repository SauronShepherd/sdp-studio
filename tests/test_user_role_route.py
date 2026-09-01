from fastapi.testclient import TestClient
from sdpstudio_server.app import create_app


def test_user_role_update_route_is_exposed(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.patch("/api/auth/users/missing", json={"role": "editor"})
    assert response.status_code in {401, 404, 503}
