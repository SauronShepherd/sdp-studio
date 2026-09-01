"""Typed, centralized server configuration with zero-credential defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerSettings:
    data_root: Path
    database_url: str
    auth_token: str = ""
    auth_signing_key: str = ""
    admin_password: str = ""
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_redirect_uri: str = ""
    oidc_client_secret: str = ""
    oidc_token_endpoint: str = ""
    oidc_userinfo_endpoint: str = ""
    oidc_jwks_uri: str = ""
    cookie_secure: bool = False

    @classmethod
    def from_env(cls, data_root: Path | None = None) -> ServerSettings:
        configured_root = os.environ.get("SDPSTUDIO_DATA_ROOT", "").strip()
        root = (
            (
                data_root
                or (Path(configured_root) if configured_root else Path.home() / ".sdpstudio")
            )
            .expanduser()
            .resolve()
        )
        return cls(
            data_root=root,
            database_url=os.environ.get("SDPSTUDIO_DATABASE_URL", "").strip(),
            auth_token=os.environ.get("SDPSTUDIO_AUTH_TOKEN", ""),
            auth_signing_key=os.environ.get("SDPSTUDIO_AUTH_SIGNING_KEY", ""),
            admin_password=os.environ.get("SDPSTUDIO_ADMIN_PASSWORD", ""),
            oidc_issuer=os.environ.get("SDPSTUDIO_OIDC_ISSUER", ""),
            oidc_client_id=os.environ.get("SDPSTUDIO_OIDC_CLIENT_ID", ""),
            oidc_redirect_uri=os.environ.get("SDPSTUDIO_OIDC_REDIRECT_URI", ""),
            oidc_client_secret=os.environ.get("SDPSTUDIO_OIDC_CLIENT_SECRET", ""),
            oidc_token_endpoint=os.environ.get("SDPSTUDIO_OIDC_TOKEN_ENDPOINT", ""),
            oidc_userinfo_endpoint=os.environ.get("SDPSTUDIO_OIDC_USERINFO_ENDPOINT", ""),
            oidc_jwks_uri=os.environ.get("SDPSTUDIO_OIDC_JWKS_URI", ""),
            cookie_secure=os.environ.get("SDPSTUDIO_COOKIE_SECURE", "0") == "1",
        )
