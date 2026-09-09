from __future__ import annotations

import os
import sysconfig
from pathlib import Path


def configure_installed_migrations_default(*, data_root: str | None = None) -> Path | None:
    """Point legacy migration discovery at wheel-installed release data.

    An explicit SDPSTUDIO_MIGRATIONS_PATH always wins. Source checkouts keep using
    their repository migration tree because DataStore checks that path first; this
    fallback only supplies the path that an installed wheel otherwise lacks.
    """

    configured = os.environ.get("SDPSTUDIO_MIGRATIONS_PATH")
    if configured:
        return Path(configured).expanduser()

    install_data = Path(data_root or sysconfig.get_path("data"))
    migration_root = install_data / "share" / "sdpstudio" / "migrations"
    if (migration_root / "env.py").is_file() and (migration_root / "versions").is_dir():
        os.environ["SDPSTUDIO_MIGRATIONS_PATH"] = str(migration_root)
        return migration_root
    return None
