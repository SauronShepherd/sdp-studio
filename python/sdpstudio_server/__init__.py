from .migration_paths import configure_installed_migrations_default

configure_installed_migrations_default()

from .app import create_app  # noqa: E402

__all__ = ["create_app"]
