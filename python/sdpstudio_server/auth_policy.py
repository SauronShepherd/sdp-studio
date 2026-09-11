from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2}


def role_allowed(
    identity: Mapping[str, Any] | None,
    minimum: str,
    *,
    auth_required: bool,
) -> bool:
    """Return whether an HTTP identity satisfies a role boundary.

    When authentication is configured, an absent local identity is never a
    privileged identity. This deliberately prevents a shared bearer token from
    implicitly becoming an administrator at role-protected endpoints.
    """
    if minimum not in ROLE_RANK:
        raise ValueError(f"Unknown minimum role: {minimum}")
    if identity is None:
        return not auth_required
    return ROLE_RANK.get(str(identity.get("role")), -1) >= ROLE_RANK[minimum]


def websocket_auth_required(
    shared_token: str | None,
    *,
    auth_service_present: bool,
) -> bool:
    """Return whether a WebSocket handshake must present authentication."""
    return bool(shared_token or auth_service_present)
