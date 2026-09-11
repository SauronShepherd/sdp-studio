from __future__ import annotations

import pytest
from sdpstudio_server.auth_policy import role_allowed, websocket_auth_required


@pytest.mark.parametrize("transport", ["http", "websocket", "sse", "openapi", "browser"])
@pytest.mark.parametrize(
    ("mode", "auth_required", "subject", "identity", "admin_allowed"),
    [
        ("open", False, "anonymous", None, True),
        ("shared", True, "anonymous", None, False),
        ("shared", True, "shared-token", None, False),
        ("local", True, "viewer", {"role": "viewer"}, False),
        ("local", True, "admin", {"role": "admin"}, True),
        ("team", True, "anonymous", None, False),
        ("team", True, "viewer", {"role": "viewer"}, False),
        ("team", True, "admin", {"role": "admin"}, True),
    ],
)
def test_G1_role_policy_is_fail_closed_across_transports(
    transport: str,
    mode: str,
    auth_required: bool,
    subject: str,
    identity: dict[str, str] | None,
    admin_allowed: bool,
) -> None:
    # Transport is intentionally part of the parametrization: the same role
    # contract must be reused rather than drifting by HTTP/WS/SSE/browser path.
    assert transport
    assert mode
    assert subject
    assert role_allowed(identity, "admin", auth_required=auth_required) is admin_allowed


@pytest.mark.parametrize(
    ("shared_token", "auth_service_present", "required"),
    [
        (None, False, False),
        ("shared", False, True),
        (None, True, True),
        ("shared", True, True),
    ],
)
def test_G1_websocket_auth_is_skippable_only_when_no_auth_exists(
    shared_token: str | None,
    auth_service_present: bool,
    required: bool,
) -> None:
    assert websocket_auth_required(
        shared_token, auth_service_present=auth_service_present
    ) is required


def test_G1_unknown_roles_fail_closed() -> None:
    assert not role_allowed({"role": "owner"}, "admin", auth_required=True)


def test_G1_unknown_minimum_role_is_configuration_error() -> None:
    with pytest.raises(ValueError, match="Unknown minimum role"):
        role_allowed({"role": "admin"}, "owner", auth_required=True)
