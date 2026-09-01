from pathlib import Path

import pytest
from sdpstudio_server.database import (
    configured_url,
    create_engine,
    initialize_database,
    initialize_sqlite,
    sqlite_url,
    transaction,
)


@pytest.mark.asyncio
async def test_async_sqlite_engine_enables_wal_and_transactions(tmp_path: Path):
    engine = create_engine(sqlite_url(tmp_path / "server.db"))
    await initialize_sqlite(engine)
    async with transaction(engine) as connection:
        await connection.exec_driver_sql("CREATE TABLE sample (value INTEGER NOT NULL)")
        await connection.exec_driver_sql("INSERT INTO sample(value) VALUES (7)")
    async with engine.connect() as connection:
        row = (await connection.exec_driver_sql("SELECT value FROM sample")).first()
        journal = (await connection.exec_driver_sql("PRAGMA journal_mode")).scalar()
    assert row[0] == 7
    assert journal.lower() == "wal"
    await engine.dispose()


def test_configured_url_defaults_to_sqlite_and_accepts_postgres(monkeypatch, tmp_path: Path):
    assert configured_url(tmp_path).startswith("sqlite+aiosqlite:///")
    monkeypatch.setenv(
        "SDPSTUDIO_DATABASE_URL", "postgresql+asyncpg://user:password@db:5432/sdpstudio"
    )
    assert configured_url(tmp_path).startswith("postgresql+asyncpg://")


@pytest.mark.asyncio
async def test_initialize_database_does_not_issue_sqlite_pragmas_for_postgres(monkeypatch):
    class Connection:
        async def execute(self, statement):
            raise AssertionError(f"unexpected backend statement: {statement}")

    class Begin:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *_):
            return False

    class Engine:
        def begin(self):
            return Begin()

    await initialize_database(Engine(), "postgresql+asyncpg://db")


def test_postgres_connection_translates_sqlite_placeholders_and_commits():
    from sdpstudio_server.storage import _PostgresConnection

    class Connection:
        def __init__(self):
            self.calls = []
            self.committed = False

        def execute(self, sql, parameters):
            self.calls.append((sql, parameters))

        def commit(self):
            self.committed = True

        def rollback(self):
            raise AssertionError("rollback should not be called")

        def close(self):
            pass

    connection = Connection()
    with _PostgresConnection(connection) as wrapped:
        wrapped.execute("UPDATE runs SET status=? WHERE id=?", ("succeeded", "run-1"))
    assert connection.calls == [("UPDATE runs SET status=%s WHERE id=%s", ("succeeded", "run-1"))]
    assert connection.committed is True


def test_runtime_bootstrap_contains_contract_fields(tmp_path: Path):
    from sdpstudio_server.storage import DataStore

    store = DataStore(tmp_path / "runtime.db")
    with store._connect() as connection:
        expected = {
            "users": {"id", "email", "display_name", "oidc_subject", "is_active", "last_login"},
            "runs": {"user_id"},
            "run_events": {"severity", "node_id", "payload_json"},
            "schedules": {"parameters_json"},
            "audit_events": {"workspace_id", "actor_user_id"},
        }
        for table, columns in expected.items():
            actual = {
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            assert columns <= actual, (table, columns - actual)
