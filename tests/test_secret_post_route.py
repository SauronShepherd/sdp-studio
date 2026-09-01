from fastapi.testclient import TestClient
from sdpstudio_server.app import create_app
from sdpstudio_server.secrets import SecretVault


def test_secret_post_uses_admin_vault_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_SECRET_KEY", "test-server-key-for-secret-post")
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/secrets",
        json={"name": "warehouse", "value": "secret-value"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "warehouse"
    assert "value" not in response.json()


def test_secret_key_rotation_reencrypts_without_exposing_plaintext(tmp_path, monkeypatch):
    old_key = "old-server-key-for-rotation"
    new_key = "new-server-key-for-rotation"
    monkeypatch.setenv("SDPSTUDIO_SECRET_KEY", old_key)
    client = TestClient(create_app(tmp_path))
    assert (
        client.post("/api/secrets", json={"name": "warehouse", "value": "secret-value"}).status_code
        == 200
    )

    old_id = SecretVault(old_key.encode()).key_id
    monkeypatch.setenv("SDPSTUDIO_SECRET_KEY", new_key)
    monkeypatch.setenv("SDPSTUDIO_SECRET_PREVIOUS_KEYS", f'{{"{old_id}": "{old_key}"}}')
    rotated = client.post("/api/secrets/rotate-key")
    assert rotated.status_code == 200
    assert rotated.json()["rotated"] == 1
    assert "value" not in rotated.json()
    assert client.app.state.store.resolve_secret("warehouse") == "secret-value"
