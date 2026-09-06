from __future__ import annotations

import pytest
from sdpstudio_server.oidc_identity import OIDCIdentity
from sdpstudio_server.oidc_roles import OIDCAuthorizationError, OIDCRoleMap


def test_role_lookup_uses_issuer_and_subject_not_email() -> None:
    roles = OIDCRoleMap({("https://idp.example", "alice-123"): "editor"})

    original = OIDCIdentity("https://idp.example", "alice-123", "alice@example.com")
    renamed = OIDCIdentity("https://idp.example", "alice-123", "alice+new@example.com")

    assert roles.role_for(original) == "editor"
    assert roles.role_for(renamed) == "editor"


def test_same_email_different_subject_does_not_inherit_role() -> None:
    roles = OIDCRoleMap({("https://idp.example", "alice-123"): "admin"})
    recycled_email = OIDCIdentity("https://idp.example", "different-user", "alice@example.com")

    with pytest.raises(OIDCAuthorizationError, match="no local role mapping"):
        roles.role_for(recycled_email)


def test_same_subject_different_issuer_does_not_inherit_role() -> None:
    roles = OIDCRoleMap({("https://idp-a.example", "subject-1"): "viewer"})
    other_provider = OIDCIdentity("https://idp-b.example", "subject-1", "user@example.com")

    with pytest.raises(OIDCAuthorizationError):
        roles.role_for(other_provider)


def test_role_map_normalizes_configured_issuer_and_subject() -> None:
    roles = OIDCRoleMap({("https://idp.example/", " subject-1 "): "viewer"})
    identity = OIDCIdentity("https://idp.example", "subject-1", "user@example.com")

    assert roles.role_for(identity) == "viewer"


@pytest.mark.parametrize("role", ["owner", "", "Editor"])
def test_role_map_rejects_unknown_local_roles(role: str) -> None:
    with pytest.raises(ValueError, match="Unknown role"):
        OIDCRoleMap({("https://idp.example", "subject-1"): role})


def test_role_map_rejects_empty_identity_components() -> None:
    with pytest.raises(ValueError, match="issuer"):
        OIDCRoleMap({("", "subject-1"): "viewer"})
    with pytest.raises(ValueError, match="subject"):
        OIDCRoleMap({("https://idp.example", " "): "viewer"})
