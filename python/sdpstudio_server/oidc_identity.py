from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .oidc import OIDCConfig


@dataclass(frozen=True, slots=True)
class OIDCIdentity:
    """Verified external identity keyed only by issuer and subject."""

    issuer: str
    subject: str
    email: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return self.issuer, self.subject


def _normalize_issuer(value: str) -> str:
    return value.strip().rstrip("/")


def identity_from_claims(config: OIDCConfig, claims: Mapping[str, object]) -> OIDCIdentity:
    issuer = _normalize_issuer(config.issuer)
    claim_issuer = claims.get("iss")
    if claim_issuer is not None and (
        not isinstance(claim_issuer, str) or _normalize_issuer(claim_issuer) != issuer
    ):
        raise ValueError("OIDC identity issuer did not match configured issuer")

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("OIDC identity subject was missing")

    email_value = claims.get("email")
    email: str | None = None
    if isinstance(email_value, str) and email_value.strip():
        # Email remains display/contact metadata only. If the provider exposes
        # email_verified it must explicitly attest the value before we retain it.
        if "email_verified" in claims and claims.get("email_verified") is not True:
            raise ValueError("OIDC identity email was not verified")
        email = email_value.strip()

    return OIDCIdentity(issuer=issuer, subject=subject.strip(), email=email)
