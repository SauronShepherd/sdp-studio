from dataclasses import dataclass

from sdpstudio_server.auth_bootstrap import AuthBootstrapService


@dataclass
class User:
    username: str
    role: str
    password_hash: str


class Registry:
    def __init__(self):
        self.loaded = []
        self.created = []

    def add_hashed_user(self, username, password_hash, role):
        self.loaded.append((username, password_hash, role))

    def add_user(self, username, password, role):
        user = User(username, role, f"hash:{password}")
        self.created.append(user)
        return user


def test_auth_bootstrap_loads_users_and_persists_optional_admin():
    registry = Registry()
    saved = []
    service = AuthBootstrapService(
        registry,
        lambda: [{"username": "editor", "password_hash": "argon", "role": "editor"}],
        lambda username, role, password_hash: saved.append((username, role, password_hash)),
    )

    service.run("administrator-password")

    assert registry.loaded == [("editor", "argon", "editor")]
    assert saved == [("admin", "admin", "hash:administrator-password")]
