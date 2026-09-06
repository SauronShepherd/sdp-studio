import pytest
from sdpstudio_server.oidc import OIDCConfig
from sdpstudio_server.oidc_identity import identity_from_claims


def _config(issuer: str = "https://issuer.example") -> OIDCConfig:
    return OIDCConfig(issuer, "client", "http://localhost/callback")


def test_oidc_identity_is_keyed_by_issuer_and_subject_not_email():
    first = identity_from_claims(
        _config(),
        {"sub": "subject-a", "email": "person@example.test", "email_verified": True},
    )
    second = identity_from_claims(
        _config(),
        {"sub": "subject-b", "email": "person@example.test", "email_verified": True},
    )
    other_issuer = identity_from_claims(
        _config("https://other.example"),
        {"sub": "subject-a", "email": "person@example.test", "email_verified": True},
    )

    assert first.key == ("https://issuer.example", "subject-a")
    assert first.key != second.key
    assert first.key != other_issuer.key


def test_oidc_identity_requires_verified_email_and_subject():
    base = {"sub": "subject", "email": "person@example.test", "email_verified": True}
    for patch, message in (
        ({"sub": ""}, "subject"),
        ({"email": ""}, "email"),
        ({"email_verified": False}, "verified"),
        ({"email_verified": None}, "verified"),
    ):
        claims = {**base, **patch}
        with pytest.raises(ValueError, match=message):
            identity_from_claims(_config(), claims)


def test_oidc_identity_rejects_mismatched_claim_issuer():
    with pytest.raises(ValueError, match="issuer"):
        identity_from_claims(
            _config(),
            {
                "iss": "https://other.example",
                "sub": "subject",
                "email": "person@example.test",
                "email_verified": True,
            },
        )
