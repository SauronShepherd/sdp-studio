from __future__ import annotations

from unittest.mock import patch

from sdpstudio_server.auth import AuthService


def test_session_is_invalid_at_exact_expiry_time():
    service = AuthService(b"auth-signing-key-1234")
    with patch("sdpstudio_server.auth.time.time", return_value=1000.0):
        token = service.issue_session("alice", "viewer", ttl=60)

    with patch("sdpstudio_server.auth.time.time", return_value=1060.0):
        assert service.verify(token) is None


def test_session_is_valid_before_expiry_time():
    service = AuthService(b"auth-signing-key-1234")
    with patch("sdpstudio_server.auth.time.time", return_value=1000.0):
        token = service.issue_session("alice", "viewer", ttl=60)

    with patch("sdpstudio_server.auth.time.time", return_value=1059.0):
        assert service.verify(token) == {"username": "alice", "role": "viewer"}
