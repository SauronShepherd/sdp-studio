import pytest
from fastapi.testclient import TestClient
from sdpstudio_server.app import create_app
from starlette.websockets import WebSocketDisconnect


def _clear(monkeypatch):
    for name in (
        "SDPSTUDIO_AUTH_TOKEN",
        "SDPSTUDIO_AUTH_SIGNING_KEY",
        "SDPSTUDIO_ADMIN_PASSWORD",
        "SDPSTUDIO_DATABASE_URL",
        "SDPSTUDIO_OIDC_ISSUER",
        "SDPSTUDIO_OIDC_CLIENT_ID",
        "SDPSTUDIO_OIDC_REDIRECT_URI",
    ):
        monkeypatch.delenv(name, raising=False)


def test_shared_bearer_does_not_gain_admin_role(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("SDPSTUDIO_AUTH_TOKEN", "shared-test-token")
    client = TestClient(create_app(tmp_path))
    r = client.get("/api/auth/users", headers={"Authorization": "Bearer shared-test-token"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "SDPS-AUTH-ROLE_REQUIRED"


def test_versioned_alias_is_authorized_before_routing(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("SDPSTUDIO_AUTH_TOKEN", "shared-test-token")
    client = TestClient(create_app(tmp_path))
    r = client.get("/api/v1/auth/users", headers={"Authorization": "Bearer shared-test-token"})
    assert r.status_code == 403


def test_cors_preflight_is_outermost(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("SDPSTUDIO_AUTH_TOKEN", "shared-test-token")
    client = TestClient(create_app(tmp_path))
    r = client.options(
        "/api/v1/auth/users",
        headers={"Origin": "http://localhost:8787", "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:8787"


def test_local_admin_session_satisfies_admin_role(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "live-wiring-signing-key")
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "admin-test-password")
    client = TestClient(create_app(tmp_path))
    assert (
        client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin-test-password"}
        ).status_code
        == 200
    )
    assert client.get("/api/auth/users").status_code == 200


def test_websocket_requires_auth_with_local_auth(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "live-wiring-signing-key")
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "admin-test-password")
    client = TestClient(create_app(tmp_path))
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        client.websocket_connect("/ws/runs/missing", subprotocols=["sdpstudio.v1"]),
    ):
        pass
    assert exc.value.code == 4401
