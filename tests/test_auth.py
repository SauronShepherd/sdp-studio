import pytest
from fastapi import Request
from sdpstudio_server.auth import AuthService


def test_auth_service_hashes_passwords_and_signs_roles():
    service = AuthService(b"auth-signing-key-1234")
    user = service.add_user("alice", "a-long-development-password", "editor")
    assert "a-long-development-password" not in user.password_hash
    token = service.login("alice", "a-long-development-password")
    assert token is not None
    assert service.verify(token) == {"username": "alice", "role": "editor"}
    assert service.login("alice", "wrong-password") is None
    assert user.password_hash.startswith("$argon2id$")
    assert service.verify(token + "x") is None


def test_auth_service_rejects_weak_passwords_and_roles():
    service = AuthService(b"auth-signing-key-1234")
    with pytest.raises(ValueError):
        service.add_user("alice", "short", "viewer")
    with pytest.raises(ValueError):
        service.add_user("alice", "a-long-development-password", "owner")


def test_auth_service_rate_limits_repeated_failures():
    service = AuthService(b"development-signing-key")
    service.add_user("alice", "a-long-development-password", "editor")
    for _ in range(5):
        assert service.login("alice", "wrong-password") is None
    assert service.login("alice", "a-long-development-password") is None


def test_role_claims_are_ordered():
    from sdpstudio_server.app import _require_role

    request = Request({"type": "http", "method": "GET", "path": "/"})
    request.state.identity = {"username": "viewer", "role": "viewer"}
    with pytest.raises(Exception, match="editor"):
        _require_role(request, "editor")
