from __future__ import annotations

from collections.abc import Mapping

from .external_principals import ExternalPrincipal, ExternalPrincipalStore
from .oidc import OIDCConfig
from .oidc_identity import identity_from_claims


def authorize_oidc_principal(
    config: OIDCConfig,
    claims: Mapping[str, object],
    principals: ExternalPrincipalStore,
) -> ExternalPrincipal:
    """Resolve verified OIDC claims to one active local authorization principal.

    Identity is derived exclusively from the configured issuer and the provider
    subject. Email is retained as metadata only and can never select a local
    account or role.
    """
    identity = identity_from_claims(config, claims)
    return principals.resolve(identity)
