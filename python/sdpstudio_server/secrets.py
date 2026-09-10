from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_V2_KEY_PREFIX = "argon2id-v2:"
_V2_CIPHERTEXT_PREFIX = "v2."
_KDF_SALT_BYTES = 16
_KDF_TIME_COST = 2
_KDF_MEMORY_COST = 19 * 1024
_KDF_PARALLELISM = 1
_KDF_HASH_LEN = 32


class SecretIntegrityError(ValueError):
    """Raised when an encrypted secret cannot be authenticated."""


@dataclass(frozen=True)
class EncryptedSecret:
    ciphertext: str
    key_id: str


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _derive_argon2id(raw: bytes, salt: bytes) -> bytes:
    return hash_secret_raw(
        secret=raw,
        salt=salt,
        time_cost=_KDF_TIME_COST,
        memory_cost=_KDF_MEMORY_COST,
        parallelism=_KDF_PARALLELISM,
        hash_len=_KDF_HASH_LEN,
        type=Type.ID,
    )


def _legacy_key(raw: bytes) -> tuple[str, bytes]:
    key = hashlib.sha256(raw).digest()
    return hashlib.sha256(key).hexdigest()[:16], key


class SecretVault:
    """AES-GCM vault with versioned Argon2id derivation and legacy recovery.

    New records use a fresh KDF salt per ciphertext and a random opaque key id,
    so the database contains neither a deterministic passphrase verifier nor a
    reusable derived key identifier. Legacy SHA-256 records remain readable for
    an explicit migration/rotation window.
    """

    def __init__(self, key: bytes | None = None, previous_keys: dict[str, bytes] | None = None):
        raw = key or os.environ.get("SDPSTUDIO_SECRET_KEY", "").encode("utf-8")
        if len(raw) < 16:
            raise ValueError("SDPSTUDIO_SECRET_KEY must contain at least 16 bytes")
        self._raw_key = raw
        self.key_id = f"{_V2_KEY_PREFIX}{_b64encode(os.urandom(8))}"
        self._previous_raw_keys: dict[str, bytes] = {}
        self._legacy_keys: dict[str, bytes] = {}

        legacy_id, legacy = _legacy_key(raw)
        self._legacy_keys[legacy_id] = legacy
        for key_id, previous in (previous_keys or {}).items():
            if len(previous) < 16:
                raise ValueError(f"Previous secret key {key_id!r} must contain at least 16 bytes")
            normalized_id = str(key_id)
            self._previous_raw_keys[normalized_id] = previous
            previous_legacy_id, previous_legacy_key = _legacy_key(previous)
            self._legacy_keys[normalized_id] = previous_legacy_key
            self._legacy_keys[previous_legacy_id] = previous_legacy_key

    @classmethod
    def from_environment(cls) -> SecretVault:
        """Load the active key and optional old keys from process configuration."""
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
        raw_previous = os.environ.get("SDPSTUDIO_SECRET_PREVIOUS_KEYS", "").strip()
        previous: dict[str, bytes] = {}
        if raw_previous:
            try:
                payload = json.loads(raw_previous)
            except json.JSONDecodeError as exc:
                raise ValueError("SDPSTUDIO_SECRET_PREVIOUS_KEYS must be valid JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError("SDPSTUDIO_SECRET_PREVIOUS_KEYS must be a JSON object")
            previous = {
                str(key_id): str(value).encode("utf-8") for key_id, value in payload.items()
            }
        return cls(active.encode("utf-8"), previous_keys=previous)

    def encrypt(self, value: str, associated_data: str = "") -> EncryptedSecret:
        salt = os.urandom(_KDF_SALT_BYTES)
        key = _derive_argon2id(self._raw_key, salt)
        nonce = os.urandom(12)
        encrypted = nonce + AESGCM(key).encrypt(
            nonce, value.encode("utf-8"), associated_data.encode("utf-8")
        )
        ciphertext = f"{_V2_CIPHERTEXT_PREFIX}{_b64encode(salt)}.{_b64encode(encrypted)}"
        return EncryptedSecret(ciphertext, self.key_id)

    def _decrypt_v2(self, secret: EncryptedSecret, associated_data: str) -> str:
        try:
            _, salt_encoded, payload_encoded = secret.ciphertext.split(".", 2)
            salt = _b64decode(salt_encoded)
            payload = _b64decode(payload_encoded)
        except (ValueError, TypeError) as exc:
            raise SecretIntegrityError("Encrypted secret format is invalid") from exc
        if len(salt) != _KDF_SALT_BYTES or len(payload) < 13:
            raise SecretIntegrityError("Encrypted secret format is invalid")

        raw_candidates = [self._raw_key]
        preferred_previous = self._previous_raw_keys.get(secret.key_id)
        if preferred_previous is not None and preferred_previous not in raw_candidates:
            raw_candidates.append(preferred_previous)
        for previous in self._previous_raw_keys.values():
            if previous not in raw_candidates:
                raw_candidates.append(previous)

        for raw in raw_candidates:
            key = _derive_argon2id(raw, salt)
            try:
                value = AESGCM(key).decrypt(
                    payload[:12], payload[12:], associated_data.encode("utf-8")
                )
                return value.decode("utf-8")
            except (InvalidTag, UnicodeDecodeError):
                continue
        raise SecretIntegrityError("Encrypted secret failed authentication")

    def decrypt(self, secret: EncryptedSecret, associated_data: str = "") -> str:
        if secret.ciphertext.startswith(_V2_CIPHERTEXT_PREFIX):
            return self._decrypt_v2(secret, associated_data)
        try:
            key = self._legacy_keys.get(secret.key_id)
            if key is None:
                raise SecretIntegrityError("Encrypted secret key version is unavailable")
            payload = base64.urlsafe_b64decode(secret.ciphertext.encode("ascii"))
            value = AESGCM(key).decrypt(payload[:12], payload[12:], associated_data.encode("utf-8"))
            return value.decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError) as exc:
            if isinstance(exc, SecretIntegrityError):
                raise
            raise SecretIntegrityError("Encrypted secret failed authentication") from exc

    def rotate(self, secret: EncryptedSecret, associated_data: str = "") -> EncryptedSecret:
        """Decrypt any supported format and re-encrypt using the active v2 format."""
        return self.encrypt(self.decrypt(secret, associated_data), associated_data)
