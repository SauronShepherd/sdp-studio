from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretIntegrityError(ValueError):
    """Raised when an encrypted secret cannot be authenticated."""


@dataclass(frozen=True)
class EncryptedSecret:
    ciphertext: str
    key_id: str


class SecretVault:
    """Small AES-GCM vault for server-side secret values.

    The key is supplied out-of-band through ``SDPSTUDIO_SECRET_KEY`` and is
    never written to the project database. A deterministic key id helps
    operators identify which external key must be available for recovery.
    """

    def __init__(self, key: bytes | None = None, previous_keys: dict[str, bytes] | None = None):
        raw = key or os.environ.get("SDPSTUDIO_SECRET_KEY", "").encode("utf-8")
        if len(raw) < 16:
            raise ValueError("SDPSTUDIO_SECRET_KEY must contain at least 16 bytes")
        self._key = hashlib.sha256(raw).digest()
        self.key_id = hashlib.sha256(self._key).hexdigest()[:16]
        self._keys = {self.key_id: self._key}
        for key_id, previous in (previous_keys or {}).items():
            if len(previous) < 16:
                raise ValueError(f"Previous secret key {key_id!r} must contain at least 16 bytes")
            self._keys[str(key_id)] = hashlib.sha256(previous).digest()

    @classmethod
    def from_environment(cls) -> SecretVault:
        """Load the active key and optional old keys from process configuration.

        ``SDPSTUDIO_SECRET_PREVIOUS_KEYS`` is a JSON object mapping key ids to
        key material. Values remain process-local and are never serialized by
        the vault or included in runtime snapshots.
        """
        active = os.environ.get("SDPSTUDIO_SECRET_KEY", "").strip()
        if not active:
            key_file = os.environ.get("SDPSTUDIO_SECRET_KEY_FILE", "").strip()
            if key_file:
                try:
                    active = Path(key_file).read_text(encoding="utf-8").strip()
                except OSError as exc:
                    raise ValueError("SDPSTUDIO_SECRET_KEY_FILE could not be read") from exc
        if not active:
            try:
                import keyring

                active = str(keyring.get_password("sdpstudio", "secret-key") or "").strip()
            except (ImportError, RuntimeError):
                active = ""
        if len(active) < 16:
            raise ValueError(
                "Configure SDPSTUDIO_SECRET_KEY, SDPSTUDIO_SECRET_KEY_FILE, or an OS keyring entry"
            )
        raw = os.environ.get("SDPSTUDIO_SECRET_PREVIOUS_KEYS", "").strip()
        previous: dict[str, bytes] = {}
        if raw:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError("SDPSTUDIO_SECRET_PREVIOUS_KEYS must be valid JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError("SDPSTUDIO_SECRET_PREVIOUS_KEYS must be a JSON object")
            previous = {
                str(key_id): str(value).encode("utf-8") for key_id, value in payload.items()
            }
        return cls(active.encode("utf-8"), previous_keys=previous)

    def encrypt(self, value: str, associated_data: str = "") -> EncryptedSecret:
        nonce = os.urandom(12)
        encrypted = nonce + AESGCM(self._key).encrypt(
            nonce, value.encode("utf-8"), associated_data.encode("utf-8")
        )
        return EncryptedSecret(base64.urlsafe_b64encode(encrypted).decode("ascii"), self.key_id)

    def decrypt(self, secret: EncryptedSecret, associated_data: str = "") -> str:
        try:
            key = self._keys.get(secret.key_id)
            if key is None:
                raise SecretIntegrityError("Encrypted secret key version is unavailable")
            payload = base64.urlsafe_b64decode(secret.ciphertext.encode("ascii"))
            value = AESGCM(key).decrypt(payload[:12], payload[12:], associated_data.encode("utf-8"))
            return value.decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError) as exc:
            raise SecretIntegrityError("Encrypted secret failed authentication") from exc

    def rotate(self, secret: EncryptedSecret, associated_data: str = "") -> EncryptedSecret:
        """Decrypt with an active or previous key and re-encrypt with the active key."""
        return self.encrypt(self.decrypt(secret, associated_data), associated_data)
