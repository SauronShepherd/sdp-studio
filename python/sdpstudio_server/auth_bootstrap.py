"""Application-start authentication user bootstrap policy."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Protocol


class AuthRegistry(Protocol):
    def add_hashed_user(self, username: str, password_hash: str, role: str) -> Any: ...

    def add_user(self, username: str, password: str, role: str) -> Any: ...


class AuthBootstrapService:
    """Load persisted identities and provision the optional local admin."""

    def __init__(
        self,
        registry: AuthRegistry,
        load_users: Callable[[], Iterable[dict[str, Any]]],
        save_user: Callable[[str, str, str], Any],
    ) -> None:
        self.registry = registry
        self.load_users = load_users
        self.save_user = save_user

    def run(self, admin_password: str | None = None) -> None:
        for user in self.load_users():
            self.registry.add_hashed_user(user["username"], user["password_hash"], user["role"])
        if admin_password:
            admin = self.registry.add_user("admin", admin_password, "admin")
            self.save_user(admin.username, admin.role, admin.password_hash)
