from __future__ import annotations

import sqlite3

import pytest
from sdpstudio_server.external_principals import (
    ExternalPrincipalAuthorizationError,
    ExternalPrincipalStore,
)
from sdpstudio_server.oidc_identity import OIDCIdentity


def _store(tmp_path):
    database = tmp_path / "principals.sqlite3"
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
        conn.execute(
            "INSERT INTO users(username,role,updated_at) VALUES(?,?,?)",
            ("local-viewer", "viewer", "now"),
        )

    def connect():
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        return conn

    return ExternalPrincipalStore(connect)


def test_same_email_different_subjects_do_not_share_role(tmp_path) -> None:
    store = _store(tmp_path)
    admin_identity = OIDCIdentity("https://issuer.example", "admin-sub", "same@example.test")
    viewer_identity = OIDCIdentity("https://issuer.example", "viewer-sub", "same@example.test")

    store.relink(admin_identity, "local-admin")
    store.relink(viewer_identity, "local-viewer")

    assert store.resolve(admin_identity).role == "admin"
    assert store.resolve(viewer_identity).role == "viewer"
    assert store.resolve(admin_identity).username != store.resolve(viewer_identity).username


def test_unlinked_subject_fails_closed_even_when_email_matches(tmp_path) -> None:
    store = _store(tmp_path)
    linked = OIDCIdentity("https://issuer.example", "linked-sub", "same@example.test")
    unknown = OIDCIdentity("https://issuer.example", "unknown-sub", "same@example.test")
    store.relink(linked, "local-admin")

    with pytest.raises(ExternalPrincipalAuthorizationError, match="not linked"):
        store.resolve(unknown)
