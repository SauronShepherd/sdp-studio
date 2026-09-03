from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

ROLES = {"viewer", "editor", "admin"}


@dataclass(frozen=True)
class User:
    username: str
    role: str
    password_hash: str


class AuthService:
    """Local authentication service with Argon2id passwords and signed sessions."""

    _password_hasher = PasswordHasher()

    def __init__(self, signing_key: bytes | None = None):
        raw = signing_key or os.environ.get("SDPSTUDIO_AUTH_SIGNING_KEY", "").encode()
        if len(raw) < 16:
            raise ValueError("SDPSTUDIO_AUTH_SIGNING_KEY must contain at least 16 bytes")
        self._key = hashlib.sha256(raw).digest()
        self._users: dict[str, User] = {}
        self._revoked: set[str] = set()
        self._login_failures: dict[str, tuple[int, float]] = {}

    @staticmethod
    def hash_password(password: str, salt: bytes | None = None) -> str:
        if len(password) < 12:
            raise ValueError("Passwords must contain at least 12 characters")
        # ``salt`` is retained only for the legacy test/migration signature;
        # Argon2id generates and stores its own random salt.
        del salt
        return AuthService._password_hasher.hash(password)

    @staticmethod
    def verify_password(password: str, encoded: str) -> bool:
        if encoded.startswith("$argon2id$"):
            try:
                return AuthService._password_hasher.verify(encoded, password)
            except (VerifyMismatchError, InvalidHashError, ValueError):
                return False
        try:
            payload = base64.urlsafe_b64decode(encoded.encode("ascii"))
            salt, expected = payload[:16], payload[16:]
            actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    def add_user(self, username: str, password: str, role: str = "viewer") -> User:
        if role not in ROLES:
            raise ValueError("Unknown role")
        user = User(username, role, self.hash_password(password))
        self._users[username] = user
        return user

    def add_hashed_user(self, username: str, password_hash: str, role: str = "viewer") -> User:
        if role not in ROLES:
            raise ValueError("Unknown role")
        user = User(username, role, password_hash)
        self._users[username] = user
        return user

    def users(self) -> tuple[User, ...]:
        return tuple(self._users[key] for key in sorted(self._users))

    def login(self, username: str, password: str) -> str | None:
        now = time.time()
        failures, locked_until = self._login_failures.get(username, (0, 0.0))
        if locked_until > now:
            return None
        user = self._users.get(username)
        if not user or not self.verify_password(password, user.password_hash):
            failures += 1
            self._login_failures[username] = (
                failures,
                now + 30 if failures >= 5 else 0.0,
            )
            return None
        self._login_failures.pop(username, None)
        return self.issue_session(user.username, user.role)

    def issue_session(self, username: str, role: str, *, ttl: int = 3600) -> str:
        if role not in ROLES:
            raise ValueError("Unknown role")
        payload = {"sub": username, "role": role, "exp": int(time.time()) + ttl}
        body = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode()
        signature = hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{signature}"

    def verify(self, token: str) -> dict[str, str] | None:
        try:
            if not token or token in self._revoked:
                return None
            body, signature = token.split(".", 1)
            if not hmac.compare_digest(
                signature, hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()
            ):
                return None
            payload = json.loads(base64.urlsafe_b64decode(body.encode()))
            if int(payload.get("exp", 0)) <= int(time.time()):
                return None
            return {"username": str(payload["sub"]), "role": str(payload["role"])}
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def revoke(self, token: str) -> None:
        if token:
            self._revoked.add(token)
