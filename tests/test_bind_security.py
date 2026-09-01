from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sdpstudio_server.app import _is_loopback_host, create_app


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "[::1]"])
def test_loopback_hosts_are_classified_safely(host):
    assert _is_loopback_host(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "studio.local"])
def test_remote_hosts_are_not_classified_as_loopback(host):
    assert not _is_loopback_host(host)


def test_app_rejects_remote_bind_without_auth(monkeypatch):
    monkeypatch.delenv("SDPSTUDIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("SDPSTUDIO_AUTH_SIGNING_KEY", raising=False)
    monkeypatch.delenv("SDPSTUDIO_OIDC_ISSUER", raising=False)
    with pytest.raises(ValueError, match="Non-loopback binds require authentication"):
        create_app(bind_host="192.168.1.20")


def test_app_allows_authenticated_remote_bind(monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_AUTH_TOKEN", "a-strong-test-token")
    app = create_app(bind_host="192.168.1.20")
    assert app.title == "SDP Studio API"


def test_oidc_issuer_without_signing_key_does_not_disable_bind_guard(monkeypatch):
    monkeypatch.delenv("SDPSTUDIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("SDPSTUDIO_AUTH_SIGNING_KEY", raising=False)
    monkeypatch.setenv("SDPSTUDIO_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("SDPSTUDIO_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("SDPSTUDIO_OIDC_REDIRECT_URI", "http://localhost/callback")
    with pytest.raises(ValueError, match="Non-loopback binds require authentication"):
        create_app(bind_host="192.168.1.20")


def test_explicit_insecure_remote_override_is_available(monkeypatch):
    monkeypatch.delenv("SDPSTUDIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("SDPSTUDIO_AUTH_SIGNING_KEY", raising=False)
    app = create_app(bind_host="192.168.1.20", allow_insecure_remote=True)
    assert app.title == "SDP Studio API"


def test_team_database_mode_requires_authentication(monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_DATABASE_URL", "postgresql://db.example/sdpstudio")
    monkeypatch.delenv("SDPSTUDIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("SDPSTUDIO_AUTH_SIGNING_KEY", raising=False)
    with pytest.raises(ValueError, match="Team mode requires authentication"):
        create_app()


def test_browser_security_headers_are_present():
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_auth_cookies_follow_https_scheme(monkeypatch, tmp_path):
    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "cookie-test-signing-key")
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "admin-test-password")
    client = TestClient(create_app(tmp_path), base_url="https://testserver")
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin-test-password"}
    )
    assert response.status_code == 200
    assert "sdpstudio_session=" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]


def test_metrics_endpoint_exposes_prometheus_counters():
    client = TestClient(create_app())
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "sdpstudio_requests_total" in response.text
    assert 'sdpstudio_request_duration_seconds_bucket{le="+Inf"}' in response.text
    for metric in (
        "sdpstudio_request_duration_seconds_count",
        "sdpstudio_active_websockets",
        "sdpstudio_runs_queued",
        "sdpstudio_runs_running",
        "sdpstudio_worker_heartbeats_total",
        "sdpstudio_schedules_fired_total",
        "sdpstudio_codegen_total",
        "sdpstudio_preview_total",
        "sdpstudio_git_operations_total",
        "sdpstudio_codegen_duration_seconds_sum",
        "sdpstudio_preview_duration_seconds_sum",
        "sdpstudio_git_operation_duration_seconds_sum",
        "sdpstudio_run_duration_seconds_sum",
    ):
        assert metric in response.text


def test_legacy_static_client_does_not_persist_bearer_tokens():
    root = Path(__file__).parents[1]
    for path in (root / "python/sdpstudio_server/static/app.js", root / "web/app.js"):
        source = path.read_text(encoding="utf-8")
        assert "localStorage.getItem('svpAuthToken')" not in source
        assert "localStorage.setItem('svpAuthToken'" not in source
