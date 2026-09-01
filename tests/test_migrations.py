from pathlib import Path

from alembic import command
from alembic.config import Config
from sdpstudio_server.storage import DataStore
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_creates_declared_persistence_schema(tmp_path: Path):
    database = tmp_path / "migration.db"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "head")

    inspector = inspect(create_engine(f"sqlite:///{database.as_posix()}"))
    tables = set(inspector.get_table_names())
    assert {
        "projects",
        "runtime_profiles",
        "runs",
        "users",
        "secrets",
        "schedules",
        "run_events",
        "audit_events",
        "workspaces",
        "workspace_members",
        "repositories",
        "documents",
        "local_revisions",
        "artifacts",
        "node_snapshots",
        "collaboration_events",
        "collaboration_snapshots",
    } <= tables
    run_columns = {column["name"] for column in inspector.get_columns("runs")}
    assert {
        "started_at",
        "finished_at",
        "exit_code",
        "error",
        "run_type",
        "graph_revision_hash",
        "git_commit",
        "git_dirty",
        "source_hash",
    } <= run_columns
    schedule_columns = {column["name"] for column in inspector.get_columns("schedules")}
    assert {"concurrency_policy", "missed_run_policy", "next_fire_at"} <= schedule_columns
    revision_columns = {column["name"] for column in inspector.get_columns("local_revisions")}
    assert {
        "document_path",
        "revision_no",
        "content_blob",
        "content_hash",
        "reason",
    } <= revision_columns
    collaboration_columns = {
        column["name"] for column in inspector.get_columns("collaboration_events")
    }
    assert {"project_id", "seq", "event_json", "created_at"} <= collaboration_columns


def test_alembic_columns_cover_runtime_bootstrap_schema(tmp_path: Path):
    runtime_root = tmp_path / "runtime"
    DataStore(runtime_root)
    runtime_db = runtime_root / "sdpstudio.db"
    runtime_inspector = inspect(create_engine(f"sqlite:///{runtime_db.as_posix()}"))
    assert "alembic_version" in runtime_inspector.get_table_names()

    migration_db = tmp_path / "alembic.db"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{migration_db.as_posix()}")
    command.upgrade(config, "head")
    migration_inspector = inspect(create_engine(f"sqlite:///{migration_db.as_posix()}"))

    for table in set(runtime_inspector.get_table_names()) - {"alembic_version"}:
        runtime_columns = {column["name"] for column in runtime_inspector.get_columns(table)}
        migration_columns = {column["name"] for column in migration_inspector.get_columns(table)}
        assert runtime_columns <= migration_columns, table


def test_alembic_spec_revision_downgrades_cleanly(tmp_path: Path):
    database = tmp_path / "rollback.db"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "head")
    command.downgrade(config, "0001_initial")
    inspector = inspect(create_engine(f"sqlite:///{database.as_posix()}"))
    assert set(inspector.get_table_names()) == {
        "projects",
        "runtime_profiles",
        "runs",
        "alembic_version",
    }


def test_contract_fields_migrate_and_downgrade_cleanly(tmp_path: Path):
    database = tmp_path / "contract-fields.db"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "head")
    inspector = inspect(create_engine(f"sqlite:///{database.as_posix()}"))
    assert {column["name"] for column in inspector.get_columns("runs")} >= {"user_id"}
    assert {column["name"] for column in inspector.get_columns("run_events")} >= {
        "severity",
        "node_id",
        "payload_json",
    }
    command.downgrade(config, "0002_spec_entities")
    inspector = inspect(create_engine(f"sqlite:///{database.as_posix()}"))
    assert "user_id" not in {column["name"] for column in inspector.get_columns("runs")}


def test_runtime_recovers_from_partial_sqlite_migration(tmp_path: Path):
    database = tmp_path / "partial" / "sdpstudio.db"
    database.parent.mkdir()
    import sqlite3

    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE projects (id TEXT PRIMARY KEY)")
    store = DataStore(database.parent)
    assert store.health_check()
    inspector = inspect(create_engine(f"sqlite:///{database.as_posix()}"))
    assert "alembic_version" in inspector.get_table_names()
