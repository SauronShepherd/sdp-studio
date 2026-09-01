import pytest
from sdpstudio_server.secrets import SecretIntegrityError, SecretVault


def test_secret_vault_encrypts_and_authenticates_values():
    vault = SecretVault(b"local-development-key-1234")
    encrypted = vault.encrypt("spark-token", associated_data="profile-1")
    assert "spark-token" not in encrypted.ciphertext
    assert vault.decrypt(encrypted, associated_data="profile-1") == "spark-token"
    with pytest.raises(SecretIntegrityError):
        vault.decrypt(encrypted, associated_data="profile-2")


def test_secret_vault_requires_external_key():
    with pytest.raises(ValueError):
        SecretVault(b"short")


def test_secret_vault_supports_previous_key_versions_and_rotation():
    old = SecretVault(b"old-development-key-1234")
    current = SecretVault(
        b"current-development-key-1234",
        previous_keys={old.key_id: b"old-development-key-1234"},
    )
    encrypted = old.encrypt("rotate-me", associated_data="secret-name")
    rotated = current.rotate(encrypted, associated_data="secret-name")
    assert rotated.key_id == current.key_id
    assert current.decrypt(encrypted, associated_data="secret-name") == "rotate-me"
    assert current.decrypt(rotated, associated_data="secret-name") == "rotate-me"
    with pytest.raises(SecretIntegrityError):
        current.decrypt(old.encrypt("rotate-me"), associated_data="secret-name")


def test_environment_vault_can_read_configured_previous_key(monkeypatch):
    old = SecretVault(b"old-development-key-1234")
    encrypted = old.encrypt("rotate-me", associated_data="secret-name")
    monkeypatch.setenv("SDPSTUDIO_SECRET_KEY", "new-development-key-1234")
    monkeypatch.setenv(
        "SDPSTUDIO_SECRET_PREVIOUS_KEYS",
        f'{{"{old.key_id}": "old-development-key-1234"}}',
    )
    assert (
        SecretVault.from_environment().decrypt(encrypted, associated_data="secret-name")
        == "rotate-me"
    )


def test_environment_vault_supports_key_file_fallback(tmp_path, monkeypatch):
    key_file = tmp_path / "secret-key"
    key_file.write_text("file-backed-development-key-1234\n", encoding="utf-8")
    monkeypatch.delenv("SDPSTUDIO_SECRET_KEY", raising=False)
    monkeypatch.setenv("SDPSTUDIO_SECRET_KEY_FILE", str(key_file))
    vault = SecretVault.from_environment()
    encrypted = vault.encrypt("file-secret")
    assert vault.decrypt(encrypted) == "file-secret"
