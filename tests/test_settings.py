from pathlib import Path

from sdpstudio_server.settings import ServerSettings


def test_settings_are_typed_and_have_zero_credential_defaults(monkeypatch, tmp_path: Path):
    for name in (
        "SDPSTUDIO_DATABASE_URL",
        "SDPSTUDIO_AUTH_TOKEN",
        "SDPSTUDIO_AUTH_SIGNING_KEY",
        "SDPSTUDIO_ADMIN_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = ServerSettings.from_env(tmp_path)
    assert settings.data_root == tmp_path.resolve()
    assert settings.database_url == ""
    assert settings.auth_token == ""
    assert settings.cookie_secure is False


def test_settings_environment_overrides_explicit_root(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SDPSTUDIO_DATABASE_URL", "postgresql+asyncpg://db/sdpstudio")
    monkeypatch.setenv("SDPSTUDIO_COOKIE_SECURE", "1")
    settings = ServerSettings.from_env(tmp_path)
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.cookie_secure is True
