from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .oidc_identity import OIDCIdentity
from .storage import utc_now


class ExternalPrincipalAuthorizationError(PermissionError):
    """Raised when an external principal is not actively linked to a local user."""


@dataclass(frozen=True, slots=True)
class ExternalPrincipal:
    issuer: str
    subject: str
    username: str
    role: str
    status: str
    email: str | None


class ExternalPrincipalStore:
    """Persistence boundary for immutable OIDC issuer+subject mappings."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    def resolve(self, identity: OIDCIdentity) -> ExternalPrincipal:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT p.issuer,p.subject,p.username,p.status,p.email,u.role "
                "FROM external_principals p JOIN users u ON u.username=p.username "
                "WHERE p.issuer=? AND p.subject=?",
                identity.key,
            ).fetchone()
        if row is None:
            raise ExternalPrincipalAuthorizationError(
                "OIDC identity is not linked to a local user; administrator relink required"
            )
        principal = ExternalPrincipal(
            issuer=str(row["issuer"]),
            subject=str(row["subject"]),
            username=str(row["username"]),
            role=str(row["role"]),
            status=str(row["status"]),
            email=str(row["email"]) if row["email"] is not None else None,
        )
        if principal.status != "active":
            raise ExternalPrincipalAuthorizationError(
                f"OIDC identity link is {principal.status}; administrator relink required"
            )
        return principal

    def relink(self, identity: OIDCIdentity, username: str) -> ExternalPrincipal:
        """Atomically bind one verified external principal to an existing local user."""

        normalized_username = username.strip()
        if not normalized_username:
            raise ValueError("username must not be empty")
        now = utc_now()
        with self._connect() as conn:
            user = conn.execute(
                "SELECT username FROM users WHERE username=?", (normalized_username,)
            ).fetchone()
            if user is None:
                raise KeyError(normalized_username)
            conn.execute(
                "INSERT INTO external_principals(issuer,subject,username,status,email,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(issuer,subject) DO UPDATE SET "
                "username=excluded.username,status='active',email=excluded.email,updated_at=excluded.updated_at",
                (
                    identity.issuer,
                    identity.subject,
                    normalized_username,
                    "active",
                    identity.email,
                    now,
                    now,
                ),
            )
            conn.execute(
                "UPDATE users SET external_identity_status='linked',updated_at=? WHERE username=?",
                (now, normalized_username),
            )
        return self.resolve(identity)

    def mark_pending_relink(self, username: str) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET external_identity_status='pending_relink',updated_at=? WHERE username=?",
                (now, username),
            )
