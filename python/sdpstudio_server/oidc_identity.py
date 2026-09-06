from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .oidc import OIDCConfig


@dataclass(frozen=True)
class OIDCIdentity:
    """Verified external identity keyed by immutable OIDC issuer and subject."""

    issuer: str
    subject: str
    email: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.issuer, self.subject)


def identity_from_claims(config: OIDCConfig, claims: Mapping[str, object]) -> OIDCIdentity:
    """Build an authorization identity from verified OIDC claims.

    Email is display/contact metadata only. Authorization identity is always the
    immutable ``(issuer, subject)`` pair so email reuse or rename cannot merge
    principals. Providers must explicitly attest that the email is verified.
    """
    issuer = config.issuer.rstrip("/")
    claim_issuer = claims.get("iss")
    if claim_issuer is not None and claim_issuer != config.issuer:
        raise ValueError("OIDC identity issuer did not match configured issuer")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("OIDC identity subject was missing")
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise ValueError("OIDC identity email was missing")
    if claims.get("email_verified") is not True:
        raise ValueError("OIDC identity email was not verified")
    return OIDCIdentity(issuer=issuer, subject=subject.strip(), email=email.strip())
