from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, replace
from threading import Lock
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class OIDCConfig:
    issuer: str
    client_id: str
    redirect_uri: str
    scopes: tuple[str, ...] = ("openid", "profile", "email")
    client_secret: str = ""
    token_endpoint: str = ""
    userinfo_endpoint: str = ""
    authorization_endpoint: str = ""
    jwks_uri: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.issuer and self.client_id and self.redirect_uri)

    def public(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "issuer": self.issuer,
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scopes": list(self.scopes),
            "has_client_secret": bool(self.client_secret),
            "discovery_configured": bool(
                self.authorization_endpoint
                or self.token_endpoint
                or self.userinfo_endpoint
                or self.jwks_uri
            ),
        }


def discover(config: OIDCConfig, *, timeout: float = 5.0) -> OIDCConfig:
    """Resolve standard OIDC endpoints from issuer discovery metadata.

    Explicit endpoint settings win, which keeps air-gapped deployments and
    test providers deterministic while still supporting generic OIDC issuers.
    """
    if not config.issuer:
        raise ValueError("OIDC issuer is not configured")
    endpoint = config.issuer.rstrip("/") + "/.well-known/openid-configuration"
    request = Request(endpoint, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        metadata = json.loads(response.read().decode("utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("OIDC discovery response was not an object")
    values = {
        "authorization_endpoint": metadata.get("authorization_endpoint"),
        "token_endpoint": metadata.get("token_endpoint"),
        "userinfo_endpoint": metadata.get("userinfo_endpoint"),
        "jwks_uri": metadata.get("jwks_uri"),
    }
    if not all(
        isinstance(values[name], str) and values[name]
        for name in ("authorization_endpoint", "token_endpoint", "userinfo_endpoint")
    ):
        raise ValueError("OIDC discovery response is missing required endpoints")
    return replace(
        config,
        authorization_endpoint=config.authorization_endpoint
        or str(values["authorization_endpoint"]),
        token_endpoint=config.token_endpoint or str(values["token_endpoint"]),
        userinfo_endpoint=config.userinfo_endpoint or str(values["userinfo_endpoint"]),
        jwks_uri=config.jwks_uri or str(values["jwks_uri"]),
    )


def exchange_code(config: OIDCConfig, code: str, *, timeout: float = 10.0) -> dict[str, object]:
    """Exchange an authorization code without exposing client secrets to callers."""
    if not config.token_endpoint:
        config = discover(config, timeout=timeout)
    if not config.enabled or not config.client_secret or not config.token_endpoint:
        raise ValueError("OIDC token exchange is not configured")
    payload = urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.redirect_uri,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
        }
    ).encode()
    request = Request(
        config.token_endpoint,
        data=payload,
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict) or not body.get("access_token"):
        raise ValueError("OIDC token response did not contain an access token")
    return body


def fetch_userinfo(
    config: OIDCConfig, access_token: str, *, timeout: float = 10.0
) -> dict[str, object]:
    if not config.userinfo_endpoint:
        config = discover(config, timeout=timeout)
    if not config.userinfo_endpoint:
        raise ValueError("OIDC userinfo endpoint is not configured")
    request = Request(
        config.userinfo_endpoint,
        headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
    )
    with urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict):
        raise ValueError("OIDC userinfo response was not an object")
    return body


def validate_id_token_nonce(
    token_response: dict[str, object],
    expected_nonce: str,
    *,
    expected_issuer: str | None = None,
    expected_audience: str | None = None,
    jwks_uri: str | None = None,
    timeout: float = 5.0,
) -> None:
    """Validate the nonce claim returned in the OIDC ID token.

    Validate claims and, when ``jwks_uri`` is supplied, the RS256 signature.
    """
    raw = token_response.get("id_token")
    if not isinstance(raw, str) or not raw:
        raise ValueError("OIDC token response did not contain an ID token")
    try:
        parts = raw.split(".")
        if len(parts) != 3:
            raise ValueError
        encoded = parts[1] + "=" * (-len(parts[1]) % 4)
        header = (
            json.loads(
                base64.urlsafe_b64decode((parts[0] + "=" * (-len(parts[0]) % 4)).encode()).decode()
            )
            if jwks_uri
            else {}
        )
        claims = json.loads(base64.urlsafe_b64decode(encoded.encode()).decode())
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("OIDC ID token was malformed") from exc
    if (
        not isinstance(header, dict)
        or not isinstance(claims, dict)
        or not hmac.compare_digest(str(claims.get("nonce", "")), expected_nonce)
    ):
        raise ValueError("OIDC ID token nonce did not match authorization state")
    if not isinstance(claims.get("sub"), str) or not claims["sub"].strip():
        raise ValueError("OIDC ID token subject was missing")
    if expected_issuer and claims.get("iss") != expected_issuer:
        raise ValueError("OIDC ID token issuer did not match configured issuer")
    if expected_audience:
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if expected_audience not in audiences:
            raise ValueError("OIDC ID token audience did not match configured client")
    if jwks_uri:
        _validate_rs256_signature(parts, header, jwks_uri, timeout=timeout)
    if "exp" in claims:
        try:
            if int(claims["exp"]) <= int(time.time()):
                raise ValueError("OIDC ID token has expired")
        except (TypeError, ValueError) as exc:
            if str(exc) == "OIDC ID token has expired":
                raise
            raise ValueError("OIDC ID token expiry was malformed") from exc
    if "iat" in claims:
        try:
            if int(claims["iat"]) > int(time.time()) + 60:
                raise ValueError("OIDC ID token issued-at time is in the future")
        except (TypeError, ValueError) as exc:
            if str(exc) == "OIDC ID token issued-at time is in the future":
                raise
            raise ValueError("OIDC ID token issued-at time was malformed") from exc


def _validate_rs256_signature(
    parts: list[str], header: dict[str, object], jwks_uri: str, *, timeout: float
) -> None:
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise ValueError("OIDC ID token must use RS256 with a key id")
    request = Request(jwks_uri, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    keys = payload.get("keys") if isinstance(payload, dict) else None
    key = next((item for item in keys or [] if item.get("kid") == header["kid"]), None)
    if not isinstance(key, dict) or key.get("kty") != "RSA":
        raise ValueError("OIDC ID token signing key was not found")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding, rsa

        modulus = int.from_bytes(base64.urlsafe_b64decode(str(key["n"]) + "=="), "big")
        exponent = int.from_bytes(base64.urlsafe_b64decode(str(key["e"]) + "=="), "big")
        public_key = rsa.RSAPublicNumbers(exponent, modulus).public_key()
        signature = base64.urlsafe_b64decode(parts[2] + "==")
        public_key.verify(
            signature, f"{parts[0]}.{parts[1]}".encode(), padding.PKCS1v15(), hashes.SHA256()
        )
    except (KeyError, ValueError, TypeError, OSError, InvalidSignature) as exc:
        raise ValueError("OIDC ID token signature was invalid") from exc


class OIDCState:
    """Signed short-lived state/nonce values for an optional OIDC flow."""

    def __init__(self, signing_key: bytes | None = None):
        raw = signing_key or os.environ.get("SDPSTUDIO_AUTH_SIGNING_KEY", "").encode()
        if len(raw) < 16:
            raise ValueError("OIDC state signing key must contain at least 16 bytes")
        self._key = hashlib.sha256(raw).digest()
        self._used: set[str] = set()
        self._lock = Lock()

    def issue(self, return_to: str = "/") -> str:
        now = int(time.time())
        nonce = secrets.token_urlsafe(24)
        body = base64.urlsafe_b64encode(f"{now}:{nonce}:{return_to}".encode()).decode()
        signature = hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{signature}"

    def verify(self, state: str, max_age: int = 600) -> dict[str, str] | None:
        try:
            body, signature = state.split(".", 1)
            expected = hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return None
            created, nonce, return_to = base64.urlsafe_b64decode(body).decode().split(":", 2)
            if int(time.time()) - int(created) > max_age:
                return None
            return {"nonce": nonce, "return_to": return_to}
        except (ValueError, UnicodeDecodeError):
            return None

    def consume(self, state: str, max_age: int = 600) -> dict[str, str] | None:
        payload = self.verify(state, max_age)
        if payload is None:
            return None
        with self._lock:
            if state in self._used:
                return None
            self._used.add(state)
            if len(self._used) > 10_000:
                self._used = set(list(self._used)[-5_000:])
        return payload


def authorization_url(config: OIDCConfig, state: str, nonce: str) -> str:
    if not config.enabled:
        raise ValueError("OIDC is not configured")
    if not config.authorization_endpoint:
        try:
            config = discover(config)
        except (OSError, ValueError, TimeoutError):
            # Development/test issuers may intentionally expose only the
            # conventional endpoint; explicit endpoint configuration remains
            # available for providers with non-standard paths.
            config = replace(
                config, authorization_endpoint=config.issuer.rstrip("/") + "/authorize"
            )
    return (
        config.authorization_endpoint
        + "?"
        + urlencode(
            {
                "client_id": config.client_id,
                "redirect_uri": config.redirect_uri,
                "response_type": "code",
                "scope": " ".join(config.scopes),
                "state": state,
                "nonce": nonce,
            }
        )
    )
