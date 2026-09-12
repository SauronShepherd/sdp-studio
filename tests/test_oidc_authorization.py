from __future__ import annotations

import sqlite3

import pytest
from sdpstudio_server.external_principals import (
    ExternalPrincipalAuthorizationError,
    ExternalPrincipalStore,
)
from sdpstudio_server.oidc import OIDCConfig
from sdpstudio_server.oidc_authorization import authorize_oidc_principal
from sdpstudio_server.oidc_identity import OIDCIdentity


def _principals(tmp_path) -> ExternalPrincipalStore:
    database = tmp_path / "oidc-authorization.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
                username TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                external_identity_status TEXT NOT NULL DEFAULT 'local'
            );
            CREATE TABLE external_principals (
                issuer TEXT NOT NULL,
                subject TEXT NOT NULL,
                username TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                email TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (issuer, subject),
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            "INSERT INTO users(username,role,updated_at) VALUES(?,?,?)",
            ("local-admin", "admin", "now"),
        )

    def connect():
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        return conn

    return ExternalPrincipalStore(connect)


def _config() -> OIDCConfig:
    return OIDCConfig(
        issuer="https://issuer.example",
        client_id="client",
        redirect_uri="https://studio.example/callback",
    )


def test_authorization_uses_issuer_and_subject_not_email(tmp_path) -> None:
    principals = _principals(tmp_path)
    principals.relink(
        OIDCIdentity("https://issuer.example", "admin-sub", "admin@example.test"),
        "local-admin",
    )

    principal = authorize_oidc_principal(
        _config(),
        {
            "iss": "https://issuer.example",
            "sub": "admin-sub",
            "email": "different@example.test",
            "email_verified": True,
        },
        principals,
    )

    assert principal.username == "local-admin"
    assert principal.role == "admin"


def test_matching_email_cannot_authorize_a_different_subject(tmp_path) -> None:
    principals = _principals(tmp_path)
    principals.relink(
        OIDCIdentity("https://issuer.example", "admin-sub", "same@example.test"),
        "local-admin",
    )

    with pytest.raises(ExternalPrincipalAuthorizationError, match="not linked"):
        authorize_oidc_principal(
            _config(),
            {
                "iss": "https://issuer.example",
                "sub": "attacker-sub",
                "email": "same@example.test",
                "email_verified": True,
            },
            principals,
        )


def test_issuer_mismatch_is_rejected_before_role_resolution(tmp_path) -> None:
    principals = _principals(tmp_path)

    with pytest.raises(ValueError, match="issuer did not match"):
        authorize_oidc_principal(
            _config(),
            {"iss": "https://other.example", "sub": "subject"},
            principals,
        )
