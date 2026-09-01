from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from .settings import ServerSettings


def sqlite_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.resolve().as_posix()}"


def configured_url(data_root: Path) -> str:
    """Return the configured team database or the zero-config local database."""
    value = ServerSettings.from_env(data_root).database_url
    if value:
        return value
    return sqlite_url(data_root / "sdpstudio.db")


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    # Route-scoped app instances and TestClient lifecycles are short-lived;
    # NullPool ensures aiosqlite worker threads are closed with each connection.
    return create_async_engine(database_url, echo=echo, poolclass=NullPool, pool_pre_ping=True)


async def initialize_sqlite(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA journal_mode=WAL"))
        await connection.execute(text("PRAGMA foreign_keys=ON"))


async def initialize_database(engine: AsyncEngine, database_url: str) -> None:
    """Apply backend-specific connection initialization."""
    if database_url.startswith("sqlite"):
        await initialize_sqlite(engine)


@asynccontextmanager
async def transaction(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with engine.begin() as connection:
        yield connection
