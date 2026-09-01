import json

import pytest
from sdpstudio_server import oidc
from sdpstudio_server.oidc import OIDCConfig, OIDCState, authorization_url, validate_id_token_nonce


def test_oidc_state_is_signed_and_expires():
    state = OIDCState(b"oidc-signing-key-1234")
    value = state.issue("/projects")
    assert state.verify(value)["return_to"] == "/projects"
    assert state.verify(value + "x") is None
    assert state.consume(value) is not None
    assert state.consume(value) is None


def test_oidc_authorization_url_has_safe_public_parameters():
    config = OIDCConfig("https://issuer.example", "client", "http://localhost/callback")
    url = authorization_url(config, "state", "nonce")
    assert "client_id=client" in url
    assert "scope=openid+profile+email" in url
    with pytest.raises(ValueError):
        authorization_url(OIDCConfig("", "", ""), "state", "nonce")


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def test_oidc_code_exchange_and_userinfo_keep_secret_out_of_requests(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout=0):
        calls.append((request.full_url, request.get_header("Authorization"), request.data))
        if request.full_url.endswith("/token"):
            return _Response({"access_token": "access", "token_type": "Bearer"})
        return _Response({"sub": "subject-1", "email": "person@example.test"})

    monkeypatch.setattr(oidc, "urlopen", fake_urlopen)
    config = OIDCConfig(
        "https://issuer.example",
        "client",
        "http://localhost/callback",
        client_secret="super-secret",
        token_endpoint="https://issuer.example/token",
        userinfo_endpoint="https://issuer.example/userinfo",
    )
    token = oidc.exchange_code(config, "code")
    claims = oidc.fetch_userinfo(config, token["access_token"])
    assert claims["email"] == "person@example.test"
    assert calls[0][0].endswith("/token")
    assert b"super-secret" in calls[0][2]
    assert calls[1][1] == "Bearer access"


def test_oidc_discovery_resolves_standard_endpoints(monkeypatch):
    payload = {
        "authorization_endpoint": "https://issuer.example/auth",
        "token_endpoint": "https://issuer.example/token",
        "userinfo_endpoint": "https://issuer.example/userinfo",
    }
    monkeypatch.setattr(oidc, "urlopen", lambda request, timeout=0: _Response(payload))
    resolved = oidc.discover(OIDCConfig("https://issuer.example", "client", "http://localhost/cb"))
    assert resolved.authorization_endpoint == payload["authorization_endpoint"]
    assert resolved.token_endpoint == payload["token_endpoint"]
    assert resolved.userinfo_endpoint == payload["userinfo_endpoint"]


def test_oidc_id_token_nonce_is_required_and_bound_to_state():
    import base64

    def token(nonce):
        payload = (
            base64.urlsafe_b64encode(json.dumps({"nonce": nonce, "sub": "subject"}).encode())
            .decode()
            .rstrip("=")
        )
        return f"header.{payload}.signature"

    validate_id_token_nonce({"id_token": token("expected")}, "expected")
    with pytest.raises(ValueError, match="nonce"):
        validate_id_token_nonce({"id_token": token("wrong")}, "expected")
    with pytest.raises(ValueError, match="ID token"):
        validate_id_token_nonce({"access_token": "access"}, "expected")


def test_oidc_id_token_validates_issuer_audience_and_expiry():
    import base64
    import time

    def token(claims):
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        return f"header.{payload}.signature"

    valid = token(
        {
            "nonce": "expected",
            "sub": "subject",
            "iss": "https://issuer.example",
            "aud": "client",
            "exp": int(time.time()) + 60,
        }
    )
    validate_id_token_nonce(
        {"id_token": valid},
        "expected",
        expected_issuer="https://issuer.example",
        expected_audience="client",
    )
    for claims, message in (
        (
            {"nonce": "expected", "sub": "subject", "iss": "https://other", "aud": "client"},
            "issuer",
        ),
        (
            {
                "nonce": "expected",
                "sub": "subject",
                "iss": "https://issuer.example",
                "aud": "other",
            },
            "audience",
        ),
        (
            {
                "nonce": "expected",
                "sub": "subject",
                "iss": "https://issuer.example",
                "aud": "client",
                "exp": 1,
            },
            "expired",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            validate_id_token_nonce(
                {"id_token": token(claims)},
                "expected",
                expected_issuer="https://issuer.example",
                expected_audience="client",
            )


def test_oidc_id_token_validates_rs256_signature_from_jwks(monkeypatch):
    import base64

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_numbers()

    def enc(value):
        return (
            base64.urlsafe_b64encode(value.to_bytes((value.bit_length() + 7) // 8, "big"))
            .decode()
            .rstrip("=")
        )

    header = {"alg": "RS256", "kid": "test-key", "typ": "JWT"}
    claims = {
        "nonce": "expected",
        "sub": "subject",
        "iss": "https://issuer.example",
        "aud": "client",
    }

    def encoded(value):
        return (
            base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode())
            .decode()
            .rstrip("=")
        )

    signing_input = f"{encoded(header)}.{encoded(claims)}"
    signature = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    token = f"{signing_input}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"

    monkeypatch.setattr(
        oidc,
        "urlopen",
        lambda request, timeout=0: _Response(
            {"keys": [{"kty": "RSA", "kid": "test-key", "n": enc(public.n), "e": enc(public.e)}]}
        ),
    )
    validate_id_token_nonce({"id_token": token}, "expected", jwks_uri="https://issuer/jwks")
    with pytest.raises(ValueError, match="signature"):
        validate_id_token_nonce(
            {"id_token": token[:-2] + "xx"}, "expected", jwks_uri="https://issuer/jwks"
        )
