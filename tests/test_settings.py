from pathlib import Path

import pytest

from sdpstudio_server.settings import ServerSettings


def test_settings_are_typed_and_have_zero_credential_defaults(monkeypatch, tmp_path: Path):
    for name in (
        "SDPSTUDIO_DATABASE_URL",
        "SDPSTUDIO_AUTH_TOKEN",
        "SDPSTUDIO_AUTH_SIGNING_KEY",
        "SDPSTUDIO_ADMIN_PASSWORD",
        "SDPSTUDIO_PUBLIC_URL",
        "SDPSTUDIO_COOKIE_SECURE",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = ServerSettings.from_env(tmp_path)
    assert settings.data_root == tmp_path.resolve()
    assert settings.database_url == ""
    assert settings.auth_token == ""
    assert settings.public_url == ""
    assert settings.cookie_secure is False


def test_settings_environment_overrides_explicit_root(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SDPSTUDIO_DATABASE_URL", "postgresql+asyncpg://db/sdpstudio")
    monkeypatch.setenv("SDPSTUDIO_COOKIE_SECURE", "1")
    settings = ServerSettings.from_env(tmp_path)
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.cookie_secure is True


def test_https_public_url_enables_secure_cookies_even_with_false_override(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setenv("SDPSTUDIO_PUBLIC_URL", "https://studio.example.test/")
    monkeypatch.setenv("SDPSTUDIO_COOKIE_SECURE", "0")
    settings = ServerSettings.from_env(tmp_path)
    assert settings.public_url == "https://studio.example.test"
    assert settings.cookie_secure is True


def test_http_public_url_does_not_enable_secure_cookies(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SDPSTUDIO_PUBLIC_URL", "http://127.0.0.1:8787")
    monkeypatch.delenv("SDPSTUDIO_COOKIE_SECURE", raising=False)
    settings = ServerSettings.from_env(tmp_path)
    assert settings.cookie_secure is False


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SDPSTUDIO_PUBLIC_URL", "studio.example.test"),
        ("SDPSTUDIO_PUBLIC_URL", "ftp://studio.example.test"),
        ("SDPSTUDIO_COOKIE_SECURE", "yes"),
    ],
)
def test_invalid_https_deployment_settings_fail_closed(
    monkeypatch, tmp_path: Path, name: str, value: str
):
    monkeypatch.delenv("SDPSTUDIO_PUBLIC_URL", raising=False)
    monkeypatch.delenv("SDPSTUDIO_COOKIE_SECURE", raising=False)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        ServerSettings.from_env(tmp_path)
