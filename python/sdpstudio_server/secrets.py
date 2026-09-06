from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_KDF_PREFIX = "argon2id-v2:"
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


def _derive_key(raw: bytes, salt: bytes) -> bytes:
    return hash_secret_raw(
        secret=raw,
        salt=salt,
        time_cost=_KDF_TIME_COST,
        memory_cost=_KDF_MEMORY_COST,
        parallelism=_KDF_PARALLELISM,
        hash_len=_KDF_HASH_LEN,
        type=Type.ID,
    )


def _key_id_for_salt(salt: bytes) -> str:
    encoded = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    return f"{_KDF_PREFIX}{encoded}"


def _salt_from_key_id(key_id: str) -> bytes | None:
    if not key_id.startswith(_KDF_PREFIX):
        return None
    encoded = key_id[len(_KDF_PREFIX) :]
    try:
        salt = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, binascii.Error) as exc:
        raise SecretIntegrityError("Encrypted secret key version is invalid") from exc
    if len(salt) != _KDF_SALT_BYTES:
        raise SecretIntegrityError("Encrypted secret key version is invalid")
    return salt


def _legacy_key(raw: bytes) -> tuple[str, bytes]:
    key = hashlib.sha256(raw).digest()
    return hashlib.sha256(key).hexdigest()[:16], key


class SecretVault:
    """Small AES-GCM vault for server-side secret values.

    The passphrase is supplied out-of-band through ``SDPSTUDIO_SECRET_KEY`` and
    is never written to the project database. New records store only an
    Argon2id KDF version and random salt as ``key_id``; the database therefore
    does not contain a fast verifier derived from the passphrase. Legacy
    SHA-256-derived records remain readable so operators can rotate them in
    place.
    """

    def __init__(self, key: bytes | None = None, previous_keys: dict[str, bytes] | None = None):
        raw = key or os.environ.get("SDPSTUDIO_SECRET_KEY", "").encode("utf-8")
        if len(raw) < 16:
            raise ValueError("SDPSTUDIO_SECRET_KEY must contain at least 16 bytes")
        self._raw_key = raw
        active_salt = os.urandom(_KDF_SALT_BYTES)
        self._key = _derive_key(raw, active_salt)
        self.key_id = _key_id_for_salt(active_salt)
        self._keys = {self.key_id: self._key}

        legacy_id, legacy_key = _legacy_key(raw)
        self._keys[legacy_id] = legacy_key
        for key_id, previous in (previous_keys or {}).items():
            if len(previous) < 16:
                raise ValueError(f"Previous secret key {key_id!r} must contain at least 16 bytes")
            normalized_id = str(key_id)
            salt = _salt_from_key_id(normalized_id)
            self._keys[normalized_id] = (
                _derive_key(previous, salt) if salt is not None else hashlib.sha256(previous).digest()
            )

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

    def _resolve_key(self, key_id: str) -> bytes | None:
        key = self._keys.get(key_id)
        if key is not None:
            return key
        salt = _salt_from_key_id(key_id)
        if salt is None:
            return None
        key = _derive_key(self._raw_key, salt)
        self._keys[key_id] = key
        return key

    def decrypt(self, secret: EncryptedSecret, associated_data: str = "") -> str:
        key = self._resolve_key(secret.key_id)
        if key is None:
            raise SecretIntegrityError("Encrypted secret key version is unavailable")
        try:
            payload = base64.urlsafe_b64decode(secret.ciphertext.encode("ascii"))
            value = AESGCM(key).decrypt(payload[:12], payload[12:], associated_data.encode("utf-8"))
            return value.decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError) as exc:
            raise SecretIntegrityError("Encrypted secret failed authentication") from exc

    def rotate(self, secret: EncryptedSecret, associated_data: str = "") -> EncryptedSecret:
        """Decrypt with an active or previous key and re-encrypt with the active key."""
        return self.encrypt(self.decrypt(secret, associated_data), associated_data)
