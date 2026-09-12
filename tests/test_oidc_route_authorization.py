from fastapi.testclient import TestClient
from sdpstudio_server.app import create_app
from sdpstudio_server.external_principals import ExternalPrincipalStore
from sdpstudio_server.oidc_identity import OIDCIdentity


def _configure_oidc(monkeypatch) -> None:
    for name in (
        "SDPSTUDIO_AUTH_TOKEN",
        "SDPSTUDIO_DATABASE_URL",
        "SDPSTUDIO_OIDC_CLIENT_SECRET",
        "SDPSTUDIO_OIDC_TOKEN_ENDPOINT",
        "SDPSTUDIO_OIDC_USERINFO_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)
    signing_key = "route-g1-" + "signing-key-123"
    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", signing_key)
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "admin-test-password")
    monkeypatch.setenv("SDPSTUDIO_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("SDPSTUDIO_OIDC_CLIENT_ID", "sdpstudio-test")
    monkeypatch.setenv("SDPSTUDIO_OIDC_REDIRECT_URI", "http://testserver/api/auth/oidc/callback")
    monkeypatch.setenv("SDPSTUDIO_OIDC_JWKS_URI", "https://issuer.example/jwks")


def test_oidc_callback_cannot_select_local_admin_by_email(monkeypatch, tmp_path) -> None:
    _configure_oidc(monkeypatch)
    app = create_app(tmp_path)
    client = TestClient(app)

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin-test-password"},
    )
    assert login.status_code == 200
    csrf = client.cookies.get("sdpstudio_csrf")
    assert csrf
    created = client.post(
        "/api/auth/users",
        headers={"x-csrf-token": csrf},
        json={
            "username": "same_example.test",
            "password": "collision-password",
            "role": "admin",
        },
    )
    assert created.status_code == 200

    monkeypatch.setattr(
        "sdpstudio_server.app.authorization_url",
        lambda config, state, nonce: f"https://issuer.example/authorize?state={state}",
    )
    monkeypatch.setattr(
        "sdpstudio_server.app.exchange_code",
        lambda config, code: {"access_token": "route-test-access", "id_token": "stub"},
    )
    monkeypatch.setattr(
        "sdpstudio_server.app.validate_id_token_nonce", lambda *args, **kwargs: None
    )

    claims = {
        "iss": "https://issuer.example",
        "sub": "unlinked-subject",
        "email": "same@example.test",
        "email_verified": True,
    }
    monkeypatch.setattr("sdpstudio_server.app.fetch_userinfo", lambda config, token: claims)

    state = client.get("/api/auth/oidc/start").json()["state"]
    rejected = client.get("/api/auth/oidc/callback", params={"code": "code-1", "state": state})
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "OIDC identity is not authorized"

    ExternalPrincipalStore(app.state.store._connect).relink(
        OIDCIdentity(
            issuer="https://issuer.example",
            subject="linked-subject",
            email="same@example.test",
        ),
        "same_example.test",
    )
    claims["sub"] = "linked-subject"
    state = client.get("/api/auth/oidc/start").json()["state"]
    accepted = client.get("/api/auth/oidc/callback", params={"code": "code-2", "state": state})
    assert accepted.status_code == 200
    assert accepted.json() == {"username": "same_example.test", "role": "admin"}
