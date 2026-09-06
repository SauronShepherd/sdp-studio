from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .auth import ROLES
from .oidc_identity import OIDCIdentity


class OIDCAuthorizationError(PermissionError):
    """Raised when an external identity has no valid local authorization mapping."""


@dataclass(frozen=True)
class OIDCRoleMap:
    """Resolve immutable OIDC identity keys to local roles.

    Mappings are keyed strictly by ``(issuer, subject)``. Email is deliberately
    excluded so address reuse or rename cannot transfer authorization.
    """

    _roles: Mapping[tuple[str, str], str]

    def __post_init__(self) -> None:
        normalized: dict[tuple[str, str], str] = {}
        for key, role in self._roles.items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise ValueError("OIDC role map keys must be (issuer, subject) tuples")
            issuer, subject = key
            if not isinstance(issuer, str) or not issuer.strip():
                raise ValueError("OIDC role map issuer must be non-empty")
            if not isinstance(subject, str) or not subject.strip():
                raise ValueError("OIDC role map subject must be non-empty")
            if role not in ROLES:
                raise ValueError(f"Unknown role: {role}")
            normalized[(issuer.rstrip("/"), subject.strip())] = role
        object.__setattr__(self, "_roles", normalized)

    def role_for(self, identity: OIDCIdentity) -> str:
        role = self._roles.get(identity.key)
        if role is None:
            raise OIDCAuthorizationError("OIDC identity has no local role mapping")
        return role
