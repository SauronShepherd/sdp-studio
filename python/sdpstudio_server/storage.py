from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

import yaml
from sdpstudio_codegen import generate_python_project, generate_sql_project
from sdpstudio_core.ids import new_ulid
from sdpstudio_core.models import (
    PipelineDocument,
    Problem,
    ProjectMetadata,
    RunRecord,
    is_valid_run_transition,
)

from .runtime_profile_service import validate_runtime_profile
from .secrets import EncryptedSecret, SecretVault


class RevisionConflictError(RuntimeError):
    def __init__(self, current_revision: int):
        super().__init__(f"Pipeline revision conflict; current revision is {current_revision}")
        self.current_revision = current_revision


class _PostgresConnection:
    """Small DB-API compatibility layer for the existing synchronous store."""

    def __init__(self, connection: Any):
        self._connection = connection

    @staticmethod
    def _parameters(sql: str) -> str:
        return sql.replace("?", "%s")

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
        return self._connection.execute(self._parameters(sql), parameters)

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def __enter__(self) -> _PostgresConnection:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc_type is None:
            self._connection.commit()
        else:
            self._connection.rollback()
        self._connection.close()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def yaml_dump(data: Any) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


class DataStore:
    def __init__(self, root: Path | None = None, database_url: str | None = None):
        configured = os.environ.get("SDPSTUDIO_DATA_ROOT")
        self.root = (
            (root or (Path(configured) if configured else Path.home() / ".sdpstudio"))
            .expanduser()
            .resolve()
        )
        self.projects_root = self.root / "projects"
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "sdpstudio.db"
        self.database_url = str(database_url or os.environ.get("SDPSTUDIO_DATABASE_URL", ""))
        self.uses_postgres = self.database_url.startswith("postgresql")
        self._lock = RLock()
        self._upgrade_schema()
        self._init_db()

    def _upgrade_schema(self) -> None:
        """Apply the repository migration chain before compatibility queries run."""
        try:
            from alembic import command
            from alembic.config import Config
        except ImportError as exc:
            raise RuntimeError(
                "Database migrations require the Alembic runtime dependency"
            ) from exc
        repository_root = Path(__file__).resolve().parents[2]
        config_path = repository_root / "alembic.ini"
        migration_root = repository_root / "migrations"
        if not migration_root.exists():
            packaged_root = Path(os.environ.get("SDPSTUDIO_MIGRATIONS_PATH", "/app/migrations"))
            config_path = packaged_root.parent / "alembic.ini"
            migration_root = packaged_root
        config = Config(str(config_path))
        config.set_main_option("script_location", str(migration_root))
        if self.uses_postgres:
            config.set_main_option("sqlalchemy.url", self.database_url)
        else:
            config.set_main_option("sqlalchemy.url", f"sqlite:///{self.db_path.as_posix()}")
            if self.db_path.exists():
                with sqlite3.connect(self.db_path) as connection:
                    tables = {
                        str(row[0])
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )
                    }
                    version_rows = (
                        connection.execute("SELECT version_num FROM alembic_version").fetchall()
                        if "alembic_version" in tables
                        else []
                    )
                if "projects" in tables and "runtime_profiles" in tables and not version_rows:
                    # SQLite DDL is non-transactional. A process interrupted
                    # during the first migration may leave a partial legacy
                    # schema; stamp it so startup can finish idempotently.
                    command.stamp(config, "head")
                    return
                if "projects" in tables and not version_rows:
                    # Recreate the base tables that may have been left out by
                    # an interrupted non-transactional SQLite migration before
                    # resuming the normal Alembic chain.
                    with sqlite3.connect(self.db_path) as connection:
                        connection.executescript(
                            """
                            CREATE TABLE IF NOT EXISTS runtime_profiles (
                                id VARCHAR(26) PRIMARY KEY,
                                name VARCHAR(120) NOT NULL,
                                adapter VARCHAR(64) NOT NULL,
                                config_json TEXT NOT NULL,
                                created_at DATETIME NOT NULL
                            );
                            CREATE TABLE IF NOT EXISTS runs (
                                id VARCHAR(26) PRIMARY KEY,
                                project_id VARCHAR(26) NOT NULL,
                                status VARCHAR(32) NOT NULL,
                                mode VARCHAR(32) NOT NULL,
                                selected_json TEXT NOT NULL,
                                command_json TEXT NOT NULL,
                                code_hash VARCHAR(64),
                                created_at DATETIME NOT NULL
                            );
                            """
                        )
                        connection.commit()
                    command.stamp(config, "0001_initial")
        command.upgrade(config, "head")

    def _connect(self) -> Any:
        if self.uses_postgres:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError(
                    "PostgreSQL persistence requires the 'postgres' installation extra"
                ) from exc
            return _PostgresConnection(
                psycopg.connect(self.database_url, row_factory=dict_row, autocommit=False)
            )
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def health_check(self) -> bool:
        """Run a minimal database probe for the application readiness contract."""
        with self._connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return True

    def _init_db(self) -> None:
        with self._connect() as conn:
            # Alembic is authoritative for current databases. The SQL below is
            # retained only as a compatibility bootstrap for legacy databases
            # that predate the migration chain or were interrupted mid-upgrade.
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            runtime_profiles_exists = (
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='runtime_profiles'"
                ).fetchone()
                is not None
            )
            if version is not None and runtime_profiles_exists:
                # The local profile is product bootstrap data, not schema. Keep
                # it available for databases created solely through Alembic.
                if conn.execute("SELECT COUNT(*) AS n FROM runtime_profiles").fetchone()["n"] == 0:
                    conn.execute(
                        "INSERT INTO runtime_profiles(id,name,adapter,config_json,created_at) VALUES(?,?,?,?,?)",
                        (new_ulid(), "Local Spark", "local", "{}", utc_now()),
                    )
                return
            # CREATE TABLE IF NOT EXISTS is not sufficient when two fresh
            # server/worker processes initialize PostgreSQL concurrently.
            # Serialize the bootstrap transaction with a database-scoped lock.
            if self.uses_postgres:
                conn.execute("SELECT pg_advisory_lock(731245901)")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  path TEXT NOT NULL UNIQUE,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  deleted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS runs (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL,
                  status TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  selected_json TEXT NOT NULL,
                  command_json TEXT NOT NULL,
                  code_hash TEXT,
                  created_at TEXT NOT NULL,
                  started_at TEXT,
                  finished_at TEXT,
                  exit_code INTEGER,
                  error TEXT,
                  pipeline_id TEXT,
                  runtime_profile_id TEXT,
                  run_type TEXT NOT NULL DEFAULT 'pipeline',
                  graph_revision_hash TEXT,
                  git_commit TEXT,
                  git_dirty INTEGER NOT NULL DEFAULT 0,
                  dirty_patch_hash TEXT,
                  source_hash TEXT,
                  external_run_id TEXT,
                  claim_token TEXT,
                  claimed_at TEXT,
                  heartbeat_at TEXT,
                  FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS runtime_profiles (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  adapter TEXT NOT NULL,
                  config_json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_events (
                  run_id TEXT NOT NULL,
                  seq INTEGER NOT NULL,
                  ts TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  message TEXT NOT NULL,
                  data_json TEXT NOT NULL,
                  PRIMARY KEY(run_id, seq),
                  FOREIGN KEY(run_id) REFERENCES runs(id)
                );
                CREATE TABLE IF NOT EXISTS schedules (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL,
                  name TEXT NOT NULL,
                  cron TEXT NOT NULL,
                  timezone TEXT NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  runtime_profile_id TEXT,
                  mode TEXT NOT NULL DEFAULT 'incremental',
                  last_claim_marker TEXT,
                  claimed_at TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS secrets (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL UNIQUE,
                  ciphertext TEXT NOT NULL,
                  key_id TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                  username TEXT PRIMARY KEY,
                  role TEXT NOT NULL,
                  password_hash TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS collaboration_events (
                  project_id TEXT NOT NULL,
                  seq INTEGER NOT NULL,
                  event_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  PRIMARY KEY(project_id, seq),
                  FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS collaboration_snapshots (
                  project_id TEXT PRIMARY KEY,
                  seq INTEGER NOT NULL,
                  document_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS workspaces (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  settings_json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_members (
                  workspace_id TEXT NOT NULL,
                  user_id TEXT NOT NULL,
                  role TEXT NOT NULL,
                  PRIMARY KEY(workspace_id, user_id),
                  FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                  id TEXT PRIMARY KEY,
                  actor TEXT NOT NULL,
                  action TEXT NOT NULL,
                  resource_type TEXT NOT NULL,
                  resource_id TEXT,
                  metadata_json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS repositories (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL,
                  remote_url_redacted TEXT NOT NULL,
                  provider_type TEXT NOT NULL,
                  default_branch TEXT NOT NULL,
                  working_copy_path TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL,
                  path TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  revision INTEGER NOT NULL,
                  content_hash TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS local_revisions (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL,
                  document_path TEXT NOT NULL,
                  revision_no INTEGER NOT NULL,
                  content_blob TEXT,
                  content_hash TEXT NOT NULL,
                  reason TEXT NOT NULL,
                  user_id TEXT,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                  id TEXT PRIMARY KEY,
                  run_id TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  path_or_uri TEXT NOT NULL,
                  content_type TEXT NOT NULL,
                  size_bytes INTEGER NOT NULL,
                  sha256 TEXT NOT NULL,
                  metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS node_snapshots (
                  id TEXT PRIMARY KEY,
                  run_id TEXT NOT NULL,
                  node_id TEXT NOT NULL,
                  schema_json TEXT,
                  profile_json TEXT,
                  metrics_json TEXT,
                  plan_artifact_id TEXT
                );
                """
            )

            def columns_for(table: str) -> set[str]:
                if self.uses_postgres:
                    return {
                        row["column_name"]
                        for row in conn.execute(
                            "SELECT column_name FROM information_schema.columns WHERE table_name=?",
                            (table,),
                        ).fetchall()
                    }
                return {
                    row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
                }

            additions = {
                "projects": {
                    "workspace_id": "TEXT",
                    "slug": "TEXT",
                    "root_path": "TEXT",
                    "repository_id": "TEXT",
                    "deleted_at": "TEXT",
                },
                "runtime_profiles": {
                    "workspace_id": "TEXT",
                    "adapter_type": "TEXT",
                    "is_protected": "INTEGER NOT NULL DEFAULT 0",
                    "updated_at": "TEXT",
                },
                "runs": {
                    "pipeline_id": "TEXT",
                    "runtime_profile_id": "TEXT",
                    "run_type": "TEXT NOT NULL DEFAULT 'pipeline'",
                    "graph_revision_hash": "TEXT",
                    "git_commit": "TEXT",
                    "git_dirty": "INTEGER NOT NULL DEFAULT 0",
                    "dirty_patch_hash": "TEXT",
                    "source_hash": "TEXT",
                    "external_run_id": "TEXT",
                    "claim_token": "TEXT",
                    "claimed_at": "TEXT",
                    "heartbeat_at": "TEXT",
                    "user_id": "TEXT",
                },
                "secrets": {
                    "workspace_id": "TEXT",
                    "encrypted_value": "TEXT",
                    "key_version": "TEXT",
                },
                "schedules": {
                    "pipeline_id": "TEXT",
                    "concurrency_policy": "TEXT",
                    "missed_run_policy": "TEXT",
                    "next_fire_at": "TEXT",
                    "last_fire_at": "TEXT",
                    "last_claim_marker": "TEXT",
                    "claimed_at": "TEXT",
                    "parameters_json": "TEXT",
                },
                "users": {
                    "id": "TEXT",
                    "email": "TEXT",
                    "display_name": "TEXT",
                    "oidc_subject": "TEXT",
                    "is_active": "INTEGER",
                    "last_login": "TEXT",
                },
                "run_events": {
                    "severity": "TEXT",
                    "node_id": "TEXT",
                    "payload_json": "TEXT",
                },
                "audit_events": {
                    "workspace_id": "TEXT",
                    "actor_user_id": "TEXT",
                },
            }
            for table, table_additions in additions.items():
                existing = columns_for(table)
                for name, definition in table_additions.items():
                    if name not in existing:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
            count = conn.execute("SELECT COUNT(*) AS n FROM runtime_profiles").fetchone()["n"]
            if count == 0:
                conn.execute(
                    "INSERT INTO runtime_profiles(id,name,adapter,config_json,created_at) VALUES(?,?,?,?,?)",
                    (new_ulid(), "Local Spark", "local", "{}", utc_now()),
                )
            if self.uses_postgres:
                conn.execute("SELECT pg_advisory_unlock(731245901)")

    def list_runtime_profiles(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM runtime_profiles ORDER BY created_at").fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["config"] = json.loads(item.pop("config_json"))
            items.append(item)
        return items

    def list_schedules(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM schedules WHERE project_id=? ORDER BY created_at", (project_id,)
            ).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            item["enabled"] = bool(item["enabled"])
        return items

    def list_secrets(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id,name,key_id,created_at,updated_at FROM secrets ORDER BY name"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT username,role,created_at,updated_at FROM users ORDER BY username"
            ).fetchall()
        return [dict(row) for row in rows]

    def append_audit_event(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "id": new_ulid(),
            "actor": actor,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "metadata": metadata or {},
            "created_at": utc_now(),
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_events(id,actor,action,resource_type,resource_id,metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (
                    event["id"],
                    event["actor"],
                    event["action"],
                    event["resource_type"],
                    event["resource_id"],
                    json.dumps(event["metadata"], sort_keys=True),
                    event["created_at"],
                ),
            )
        return event

    def list_audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id,actor,action,resource_type,resource_id,metadata_json,created_at FROM audit_events ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "actor": row["actor"],
                "action": row["action"],
                "resource_type": row["resource_type"],
                "resource_id": row["resource_id"],
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def load_users_for_auth(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT username,role,password_hash FROM users").fetchall()
        return [dict(row) for row in rows]

    def save_user(self, username: str, role: str, password_hash: str) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users(username,role,password_hash,created_at,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(username) DO UPDATE SET role=excluded.role,password_hash=excluded.password_hash,updated_at=excluded.updated_at",
                (username, role, password_hash, now, now),
            )
        return next(item for item in self.list_users() if item["username"] == username)

    def update_user_role(self, username: str, role: str) -> dict[str, Any]:
        if role not in {"viewer", "editor", "admin"}:
            raise ValueError("Unknown role")
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                raise KeyError(username)
            conn.execute(
                "UPDATE users SET role=?,updated_at=? WHERE username=?",
                (role, utc_now(), username),
            )
        return next(item for item in self.list_users() if item["username"] == username)

    def append_collaboration_event(self, project_id: str, event: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(seq) + 1 AS seq FROM ("
                "SELECT seq FROM collaboration_events WHERE project_id=? "
                "UNION ALL SELECT seq FROM collaboration_snapshots WHERE project_id=?"
                ")",
                (project_id, project_id),
            ).fetchone()
            seq = int(row["seq"] or 1)
            conn.execute(
                "INSERT INTO collaboration_events(project_id,seq,event_json,created_at) VALUES(?,?,?,?)",
                (project_id, seq, json.dumps(event, sort_keys=True), utc_now()),
            )
            # Yjs updates are durable binary deltas. Periodically retain a
            # replayable update bundle as the snapshot anchor and remove the
            # covered rows so reconnect/recovery remains bounded.
            if seq % 100 == 0:
                rows = conn.execute(
                    "SELECT seq,event_json FROM collaboration_events WHERE project_id=? ORDER BY seq",
                    (project_id,),
                ).fetchall()
                updates = [
                    json.loads(row["event_json"])
                    for row in rows
                    if json.loads(row["event_json"]).get("type") == "y_update"
                ]
                snapshot = {"format": "yjs-update-bundle", "updates": updates}
                now = utc_now()
                conn.execute(
                    "INSERT INTO collaboration_snapshots(project_id,seq,document_json,created_at) VALUES(?,?,?,?) "
                    "ON CONFLICT(project_id) DO UPDATE SET seq=excluded.seq,document_json=excluded.document_json,created_at=excluded.created_at",
                    (project_id, seq, json.dumps(snapshot, sort_keys=True), now),
                )
                conn.execute(
                    "DELETE FROM collaboration_events WHERE project_id=? AND seq<=?",
                    (project_id, seq),
                )
        return {"project_id": project_id, "seq": seq, **event}

    def collaboration_events(self, project_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT seq,event_json,created_at FROM collaboration_events WHERE project_id=? AND seq>? ORDER BY seq",
                (project_id, after),
            ).fetchall()
        return [
            {
                "project_id": project_id,
                "seq": int(row["seq"]),
                **json.loads(row["event_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def save_collaboration_snapshot(
        self, project_id: str, document: dict[str, Any], seq: int | None = None
    ) -> dict[str, Any]:
        """Persist a replay anchor so recovery does not depend on an unbounded event log."""
        with self._connect() as conn:
            if seq is None:
                row = conn.execute(
                    "SELECT COALESCE(MAX(seq),0) AS seq FROM collaboration_events WHERE project_id=?",
                    (project_id,),
                ).fetchone()
                seq = int(row["seq"])
            now = utc_now()
            conn.execute(
                "INSERT INTO collaboration_snapshots(project_id,seq,document_json,created_at) VALUES(?,?,?,?) "
                "ON CONFLICT(project_id) DO UPDATE SET seq=excluded.seq,document_json=excluded.document_json,created_at=excluded.created_at",
                (project_id, seq, json.dumps(document, sort_keys=True), now),
            )
        return {"project_id": project_id, "seq": seq, "document": document, "created_at": now}

    def collaboration_snapshot(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT project_id,seq,document_json,created_at FROM collaboration_snapshots WHERE project_id=?",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "project_id": row["project_id"],
            "seq": int(row["seq"]),
            "document": json.loads(row["document_json"]),
            "created_at": row["created_at"],
        }

    def compact_collaboration_events(self, project_id: str, keep_after: int) -> int:
        """Drop only events covered by a durable snapshot."""
        snapshot = self.collaboration_snapshot(project_id)
        if snapshot is None or int(snapshot["seq"]) < keep_after:
            return 0
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM collaboration_events WHERE project_id=? AND seq<?",
                (project_id, keep_after),
            )
        return int(result.rowcount)

    def put_secret(self, name: str, value: str) -> dict[str, Any]:
        vault = SecretVault.from_environment()
        encrypted = vault.encrypt(value, associated_data=name)
        secret_id = new_ulid()
        now = utc_now()
        with self._connect() as conn:
            existing = conn.execute("SELECT id FROM secrets WHERE name=?", (name,)).fetchone()
            if existing:
                secret_id = existing["id"]
                conn.execute(
                    "UPDATE secrets SET ciphertext=?,key_id=?,updated_at=? WHERE id=?",
                    (encrypted.ciphertext, encrypted.key_id, now, secret_id),
                )
            else:
                conn.execute(
                    "INSERT INTO secrets(id,name,ciphertext,key_id,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (secret_id, name, encrypted.ciphertext, encrypted.key_id, now, now),
                )
        return next(item for item in self.list_secrets() if item["id"] == secret_id)

    def delete_secret(self, secret_id: str) -> None:
        with self._connect() as conn:
            if conn.execute("DELETE FROM secrets WHERE id=?", (secret_id,)).rowcount == 0:
                raise KeyError(secret_id)

    def rotate_secrets(self) -> dict[str, Any]:
        """Re-encrypt every registered secret under the active vault key."""
        vault = SecretVault.from_environment()
        rotated = 0
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id,name,ciphertext,key_id FROM secrets ORDER BY name"
            ).fetchall()
            for row in rows:
                encrypted = vault.rotate(
                    EncryptedSecret(str(row["ciphertext"]), str(row["key_id"])),
                    associated_data=str(row["name"]),
                )
                conn.execute(
                    "UPDATE secrets SET ciphertext=?,key_id=?,updated_at=? WHERE id=?",
                    (encrypted.ciphertext, encrypted.key_id, utc_now(), row["id"]),
                )
                rotated += 1
        return {"rotated": rotated, "key_id": vault.key_id}

    def resolve_secret(self, name: str) -> str:
        """Resolve one secret reference for an execution boundary only."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT ciphertext,key_id FROM secrets WHERE name=?", (name,)
            ).fetchone()
        if row is None:
            raise KeyError(name)
        vault = SecretVault.from_environment()
        return vault.decrypt(
            EncryptedSecret(ciphertext=row["ciphertext"], key_id=row["key_id"]),
            associated_data=name,
        )

    def rotate_secret(self, name: str, previous_keys: dict[str, bytes]) -> dict[str, Any]:
        """Re-encrypt a stored value under the active master key."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id,ciphertext,key_id FROM secrets WHERE name=?", (name,)
            ).fetchone()
        if row is None:
            raise KeyError(name)
        vault = SecretVault(previous_keys=previous_keys)
        rotated = vault.rotate(
            EncryptedSecret(ciphertext=row["ciphertext"], key_id=row["key_id"]),
            associated_data=name,
        )
        with self._connect() as conn:
            conn.execute(
                "UPDATE secrets SET ciphertext=?,key_id=?,updated_at=? WHERE id=?",
                (rotated.ciphertext, rotated.key_id, utc_now(), row["id"]),
            )
        return next(item for item in self.list_secrets() if item["id"] == row["id"])

    def resolve_secret_references(self, project_id: str, profile: dict[str, Any]) -> dict[str, str]:
        """Collect and decrypt ``secret://NAME`` references without persisting values."""
        document = self.load_pipeline(project_id).model_dump(by_alias=True)
        references: set[str] = set()

        def collect(value: Any) -> None:
            if isinstance(value, str) and value.startswith("secret://"):
                name = value.removeprefix("secret://").strip()
                if name:
                    references.add(name)
            elif isinstance(value, dict):
                for item in value.values():
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        collect(document)
        collect(profile)
        return {name: self.resolve_secret(name) for name in sorted(references)}

    def create_schedule(
        self,
        project_id: str,
        name: str,
        cron: str,
        timezone: str = "UTC",
        enabled: bool = True,
        runtime_profile_id: str | None = None,
        mode: str = "incremental",
        concurrency_policy: str = "skip",
        missed_run_policy: str = "skip",
    ) -> dict[str, Any]:
        self.get_project_row(project_id)
        fields = cron.split()
        if len(fields) != 5:
            raise ValueError("Schedule cron must contain exactly five fields")
        if mode not in {"incremental", "refresh", "full-refresh-all"}:
            raise ValueError("Unsupported schedule mode")
        if concurrency_policy not in {"skip", "forbid", "replace"}:
            raise ValueError("Unsupported schedule concurrency policy")
        if missed_run_policy not in {"skip", "run_once"}:
            raise ValueError("Unsupported missed-run policy")
        schedule_id = new_ulid()
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO schedules(id,project_id,name,cron,timezone,enabled,runtime_profile_id,mode,concurrency_policy,missed_run_policy,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    schedule_id,
                    project_id,
                    name,
                    cron,
                    timezone,
                    int(enabled),
                    runtime_profile_id,
                    mode,
                    concurrency_policy,
                    missed_run_policy,
                    now,
                    now,
                ),
            )
        return self.get_schedule(schedule_id)

    def get_schedule(self, schedule_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)).fetchone()
        if not row:
            raise KeyError(schedule_id)
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        return item

    def update_schedule(self, schedule_id: str, updates: dict[str, Any] | bool) -> dict[str, Any]:
        if isinstance(updates, bool):
            updates = {"enabled": updates}
        allowed = {
            "enabled",
            "name",
            "cron",
            "timezone",
            "runtime_profile_id",
            "mode",
            "concurrency_policy",
            "missed_run_policy",
        }
        changes = {key: value for key, value in updates.items() if key in allowed}
        if not changes:
            raise ValueError("Schedule update contains no supported fields")
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM schedules WHERE id=?", (schedule_id,)).fetchone():
                raise KeyError(schedule_id)
            assignments = [f"{key}=?" for key in changes]
            values = [int(value) if key == "enabled" else value for key, value in changes.items()]
            conn.execute(
                f"UPDATE schedules SET {', '.join(assignments)},updated_at=? WHERE id=?",
                (*values, utc_now(), schedule_id),
            )
        return self.get_schedule(schedule_id)

    def delete_schedule(self, schedule_id: str) -> None:
        with self._connect() as conn:
            if conn.execute("DELETE FROM schedules WHERE id=?", (schedule_id,)).rowcount == 0:
                raise KeyError(schedule_id)

    def claim_schedule(self, schedule_id: str, marker: str) -> bool:
        """Atomically claim one schedule firing across processes/workers."""
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE schedules SET last_claim_marker=?,claimed_at=?,updated_at=? "
                "WHERE id=? AND enabled=1 AND (last_claim_marker IS NULL OR last_claim_marker<>?)",
                (marker, utc_now(), utc_now(), schedule_id, marker),
            )
            return result.rowcount == 1

    def get_runtime_profile(self, profile_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runtime_profiles WHERE id=?", (profile_id,)
            ).fetchone()
        if not row:
            raise KeyError(profile_id)
        item = dict(row)
        item["config"] = json.loads(item.pop("config_json"))
        return item

    def create_runtime_profile(
        self, name: str, adapter: str, config: dict[str, Any], *, is_protected: bool = False
    ) -> dict[str, Any]:
        validate_runtime_profile(adapter, config)
        profile_id = new_ulid()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runtime_profiles(id,name,adapter,config_json,is_protected,created_at) VALUES(?,?,?,?,?,?)",
                (profile_id, name, adapter, json.dumps(config), int(is_protected), utc_now()),
            )
        return self.get_runtime_profile(profile_id)

    def _validate_runtime_profile(self, adapter: str, config: dict[str, Any]) -> None:
        validate_runtime_profile(adapter, config)

    def delete_runtime_profile(self, profile_id: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT adapter FROM runtime_profiles WHERE id=?", (profile_id,)
            ).fetchone()
            if not row:
                raise KeyError(profile_id)
            if (
                row["adapter"] == "local"
                and conn.execute(
                    "SELECT COUNT(*) AS n FROM runtime_profiles WHERE adapter='local'"
                ).fetchone()["n"]
                <= 1
            ):
                raise ValueError("Cannot delete the last local runtime profile")
            conn.execute("DELETE FROM runtime_profiles WHERE id=?", (profile_id,))

    def update_runtime_profile(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        adapter: str | None = None,
        config: dict[str, Any] | None = None,
        is_protected: bool | None = None,
    ) -> dict[str, Any]:
        current = self.get_runtime_profile(profile_id)
        next_name = name or current["name"]
        next_adapter = adapter or current["adapter"]
        next_config = config if config is not None else current["config"]
        next_protected = (
            bool(is_protected) if is_protected is not None else bool(current.get("is_protected"))
        )
        # Reuse the same provider/configuration validation as creation without
        # creating a second profile.
        self._validate_runtime_profile(next_adapter, next_config)
        with self._connect() as conn:
            conn.execute(
                "UPDATE runtime_profiles SET name=?,adapter=?,config_json=?,is_protected=?,updated_at=? WHERE id=?",
                (
                    next_name,
                    next_adapter,
                    json.dumps(next_config),
                    int(next_protected),
                    utc_now(),
                    profile_id,
                ),
            )
        return self.get_runtime_profile(profile_id)

    def list_projects(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_project_row(self, project_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)
            ).fetchone()
        if not row:
            raise KeyError(project_id)
        return dict(row)

    def project_path(self, project_id: str) -> Path:
        row = self.get_project_row(project_id)
        path = Path(row["path"]).resolve()
        if self.projects_root not in path.parents:
            raise ValueError("Project path escaped workspace root")
        return path

    def _new_project_path(self, name: str, project_id: str) -> Path:
        safe_name = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-") or "project"
        path = (self.projects_root / f"{safe_name}-{project_id[-6:].lower()}").resolve()
        if self.projects_root not in path.parents:
            raise ValueError("Invalid project path")
        return path

    def clone_project(
        self, name: str, remote_url: str, branch: str | None = None
    ) -> dict[str, Any]:
        from . import git_service

        project_id = new_ulid()
        path = self._new_project_path(name, project_id)
        try:
            git_service.clone(remote_url, path, branch)
            pipeline_path = path / ".sdpstudio" / "pipelines" / "main.sdpstudio.yaml"
            metadata_path = path / ".sdpstudio" / "project.yaml"
            if not pipeline_path.exists() or not metadata_path.exists():
                raise ValueError(
                    "Repository is not an SDP Studio project: .sdpstudio/project.yaml and .sdpstudio/pipelines/main.sdpstudio.yaml are required"
                )
            raw = yaml.safe_load(pipeline_path.read_text(encoding="utf-8")) or {}
            PipelineDocument.model_validate(raw)
            metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
            if isinstance(metadata, dict) and "schemaVersion" not in metadata:
                metadata["schemaVersion"] = 1
                atomic_write(metadata_path, yaml.safe_dump(metadata, sort_keys=False))
            for directory in (
                path / ".sdpstudio" / "runtime" / "storage",
                path / ".sdpstudio" / "runtime" / "event-logs",
                path / ".sdpstudio" / "runtime" / "run-artifacts",
                path / ".sdpstudio" / "history",
            ):
                directory.mkdir(parents=True, exist_ok=True)
            # Keep machine-local execution/history files out of Git without modifying
            # the repository's tracked .gitignore on clone.
            info_exclude = path / ".git" / "info" / "exclude"
            existing = info_exclude.read_text(encoding="utf-8") if info_exclude.exists() else ""
            entries = [
                ".sdpstudio/runtime/",
                ".sdpstudio/history/",
                ".sdpstudio-runtime-*.yaml",
                "__pycache__/",
                "*.pyc",
            ]
            missing = [item for item in entries if item not in existing.splitlines()]
            if missing:
                atomic_write(
                    info_exclude,
                    existing.rstrip()
                    + ("\n" if existing.strip() else "")
                    + "\n".join(missing)
                    + "\n",
                )
            now = utc_now()
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO projects(id,name,path,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (project_id, name, str(path), now, now),
                )
            return self.get_project(project_id)
        except Exception:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
            raise

    def create_project(self, name: str, example_path: Path | None = None) -> dict[str, Any]:
        project_id = new_ulid()
        path = self._new_project_path(name, project_id)
        path.mkdir(parents=True, exist_ok=False)

        if example_path and example_path.exists():
            shutil.copytree(example_path, path, dirs_exist_ok=True)

        pipeline_path = path / ".sdpstudio" / "pipelines" / "main.sdpstudio.yaml"
        if pipeline_path.exists():
            raw = yaml.safe_load(pipeline_path.read_text(encoding="utf-8"))
            document = PipelineDocument.model_validate(raw)
            document.pipelineId = document.pipelineId or new_ulid()
            document.name = name
        else:
            document = PipelineDocument(name=name)

        metadata = ProjectMetadata(
            projectId=project_id,
            name=name,
            pipelines=[
                {"id": document.pipelineId, "model": ".sdpstudio/pipelines/main.sdpstudio.yaml"}
            ],
        )
        atomic_write(path / ".sdpstudio" / "project.yaml", yaml_dump(metadata.model_dump()))
        atomic_write(pipeline_path, yaml_dump(document.model_dump(by_alias=True)))
        (path / "transformations").mkdir(parents=True, exist_ok=True)
        (path / ".sdpstudio" / "runtime" / "storage").mkdir(parents=True, exist_ok=True)
        (path / ".sdpstudio" / "runtime" / "event-logs").mkdir(parents=True, exist_ok=True)
        (path / ".sdpstudio" / "runtime" / "run-artifacts").mkdir(parents=True, exist_ok=True)
        (path / ".sdpstudio" / "history").mkdir(parents=True, exist_ok=True)
        ignore = path / ".gitignore"
        if not ignore.exists():
            atomic_write(
                ignore,
                ".sdpstudio/runtime/\n.sdpstudio/history/\n.sdpstudio-runtime-*.yaml\n__pycache__/\n*.pyc\n",
            )
        self._write_generated(project_id, path, document, snapshot=False)

        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO projects(id,name,path,created_at,updated_at) VALUES(?,?,?,?,?)",
                (project_id, name, str(path), now, now),
            )
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict[str, Any]:
        row = self.get_project_row(project_id)
        path = Path(row["path"])
        meta = yaml.safe_load((path / ".sdpstudio" / "project.yaml").read_text(encoding="utf-8"))
        if not isinstance(meta, dict) or "schemaVersion" not in meta:
            raise ValueError("SDPS-SCHEMA-001: persisted project schemaVersion is required")
        metadata = ProjectMetadata.model_validate(meta)
        return {**row, "metadata": metadata.model_dump(by_alias=True)}

    def update_project(self, project_id: str, name: str) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("Project name must not be empty")
        current = self.get_project(project_id)
        now = utc_now()
        metadata = dict(current.get("metadata") or {})
        metadata["name"] = name
        path = self.project_path(project_id)
        atomic_write(path / ".sdpstudio" / "project.yaml", yaml_dump(metadata))
        with self._connect() as conn:
            conn.execute(
                "UPDATE projects SET name=?,updated_at=? WHERE id=?", (name, now, project_id)
            )
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> None:
        path = self.project_path(project_id)
        if self.projects_root not in path.parents:
            raise ValueError("Project path escaped workspace root")
        with self._connect() as conn:
            run_ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM runs WHERE project_id=?", (project_id,)
                ).fetchall()
            ]
            for run_id in run_ids:
                conn.execute("DELETE FROM node_snapshots WHERE run_id=?", (run_id,))
                conn.execute("DELETE FROM artifacts WHERE run_id=?", (run_id,))
                conn.execute("DELETE FROM run_events WHERE run_id=?", (run_id,))
            conn.execute("DELETE FROM runs WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM schedules WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM documents WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM local_revisions WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM repositories WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM collaboration_events WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM collaboration_snapshots WHERE project_id=?", (project_id,))
            now = utc_now()
            conn.execute(
                "UPDATE projects SET deleted_at=?,updated_at=? WHERE id=?",
                (now, now, project_id),
            )
        # Keep files and history recoverable; normal reads hide the tombstone.

    def load_pipeline(self, project_id: str) -> PipelineDocument:
        path = self.project_path(project_id) / ".sdpstudio" / "pipelines" / "main.sdpstudio.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict) or "schemaVersion" not in data:
            raise ValueError("SDPS-SCHEMA-001: persisted pipeline schemaVersion is required")
        return PipelineDocument.model_validate(data)

    def _snapshot(self, project_id: str, document: PipelineDocument, reason: str) -> dict[str, Any]:
        path = self.project_path(project_id)
        history = path / ".sdpstudio" / "history"
        history.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        snapshot_id = new_ulid()
        payload = {
            "id": snapshot_id,
            "created_at": utc_now(),
            "reason": reason,
            "revision": document.revision,
            "document": document.model_dump(by_alias=True),
        }
        atomic_write(history / f"{stamp}_{snapshot_id}.json", json.dumps(payload, indent=2) + "\n")
        files = sorted(history.glob("*.json"), reverse=True)
        try:
            max_count = max(1, int(os.environ.get("SDPSTUDIO_HISTORY_MAX_COUNT", "200")))
        except ValueError:
            max_count = 200
        try:
            max_age_days = max(0.0, float(os.environ.get("SDPSTUDIO_HISTORY_MAX_AGE_DAYS", "365")))
        except ValueError:
            max_age_days = 365.0
        cutoff = datetime.now(UTC).timestamp() - max_age_days * 86400
        for index, old in enumerate(files):
            if index >= max_count or old.stat().st_mtime < cutoff:
                old.unlink(missing_ok=True)
        return {k: payload[k] for k in ("id", "created_at", "reason", "revision")}

    def create_history_checkpoint(self, project_id: str, name: str) -> dict[str, Any]:
        if not name or len(name) > 120 or any(char in name for char in "/\\"):
            raise ValueError("Invalid history checkpoint name")
        return self._snapshot(project_id, self.load_pipeline(project_id), f"checkpoint: {name}")

    def save_pipeline(self, project_id: str, document: PipelineDocument) -> PipelineDocument:
        with self._lock:
            current = self.load_pipeline(project_id)
            if document.revision != current.revision:
                raise RevisionConflictError(current.revision)
            # Coalesce rapid canvas edits into one undo/history checkpoint.
            # Explicit checkpoints and Git pre-mutation snapshots remain
            # unconditional; this applies only to the automatic edit snapshot.
            history = self.project_path(project_id) / ".sdpstudio" / "history"
            latest = max(
                history.glob("*.json"), default=None, key=lambda item: item.stat().st_mtime
            )
            try:
                debounce_seconds = max(
                    0.0, float(os.environ.get("SDPSTUDIO_HISTORY_DEBOUNCE_SECONDS", "2"))
                )
            except ValueError:
                debounce_seconds = 2.0
            if (
                latest is None
                or datetime.now(UTC).timestamp() - latest.stat().st_mtime >= debounce_seconds
            ):
                self._snapshot(project_id, current, "before visual edit")
            document.revision = current.revision + 1
            path = (
                self.project_path(project_id) / ".sdpstudio" / "pipelines" / "main.sdpstudio.yaml"
            )
            atomic_write(path, yaml_dump(document.model_dump(by_alias=True)))
            with self._connect() as conn:
                conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (utc_now(), project_id))
            return document

    def list_history(self, project_id: str) -> list[dict[str, Any]]:
        history = self.project_path(project_id) / ".sdpstudio" / "history"
        items = []
        for file in sorted(history.glob("*.json"), reverse=True):
            try:
                payload = json.loads(file.read_text(encoding="utf-8"))
                items.append(
                    {k: payload.get(k) for k in ("id", "created_at", "reason", "revision")}
                )
            except (ValueError, OSError):
                continue
        return items

    def load_history_snapshot(self, project_id: str, snapshot_id: str) -> dict[str, Any]:
        history = self.project_path(project_id) / ".sdpstudio" / "history"
        for file in history.glob(f"*_{snapshot_id}.json"):
            return json.loads(file.read_text(encoding="utf-8"))
        raise KeyError(snapshot_id)

    def restore_history(self, project_id: str, snapshot_id: str) -> PipelineDocument:
        history = self.project_path(project_id) / ".sdpstudio" / "history"
        for file in history.glob(f"*_{snapshot_id}.json"):
            payload = json.loads(file.read_text(encoding="utf-8"))
            document = PipelineDocument.model_validate(payload["document"])
            document.revision = self.load_pipeline(project_id).revision
            self.save_pipeline(project_id, document)
            return self.load_pipeline(project_id)
        raise KeyError(snapshot_id)

    def _write_generated(
        self, project_id: str, path: Path, document: PipelineDocument, snapshot: bool = True
    ):
        (path / ".sdpstudio" / "runtime" / "storage").mkdir(parents=True, exist_ok=True)
        (path / ".sdpstudio" / "runtime" / "event-logs").mkdir(parents=True, exist_ok=True)
        (path / ".sdpstudio" / "runtime" / "run-artifacts").mkdir(parents=True, exist_ok=True)
        result = generate_python_project(document, path)
        if result.files:
            source_map_path = path / ".sdpstudio" / "source-maps" / "generated.py.map.json"
            if source_map_path.exists():
                try:
                    source_map = json.loads(source_map_path.read_text(encoding="utf-8"))
                    expected_hash = (source_map.get("files") or {}).get(
                        "transformations/generated.py"
                    )
                    generated_path = path / "transformations" / "generated.py"
                    current_hash = (
                        hashlib.sha256(generated_path.read_bytes()).hexdigest()
                        if generated_path.exists()
                        else None
                    )
                    if expected_hash and current_hash != expected_hash:
                        return result.model_copy(
                            update={
                                "files": [],
                                "problems": [
                                    *result.problems,
                                    Problem(
                                        code="SDPS-CODEGEN-DRIFT",
                                        severity="error",
                                        message="Generated source changed outside SDP Studio; refusing to overwrite it.",
                                        remediation="Review or restore the generated file, then regenerate explicitly.",
                                    ),
                                ],
                            }
                        )
                except (OSError, json.JSONDecodeError, TypeError):
                    # A malformed map cannot prove ownership, so preserve the
                    # existing file rather than destructively rewriting it.
                    return result.model_copy(
                        update={
                            "files": [],
                            "problems": [
                                *result.problems,
                                Problem(
                                    code="SDPS-CODEGEN-MAP",
                                    severity="error",
                                    message="Generated source ownership metadata is unreadable; refusing to overwrite it.",
                                ),
                            ],
                        }
                    )
            if snapshot:
                self._snapshot(project_id, document, "before code generation")
            before_hashes = self._existing_generated_hashes(path, result)
            for file in result.files:
                atomic_write(path / file.path, file.content)
            source_map_payload = {
                "schemaVersion": 1,
                "mappings": [m.model_dump() for m in result.source_map],
                "files": {f.path: f.sha256 for f in result.files},
            }
            atomic_write(
                path / ".sdpstudio" / "source-maps" / "generated.py.map.json",
                json.dumps(source_map_payload, indent=2) + "\n",
            )
            result = self._generation_diff(result, before_hashes)
        return result

    def generate(self, project_id: str, write: bool = True):
        path = self.project_path(project_id)
        document = self.load_pipeline(project_id)
        result = generate_python_project(document, path)
        if write and result.files:
            return self._write_generated(project_id, path, document, snapshot=True)
        return result

    def generate_sql(self, project_id: str, write: bool = True):
        """Generate SQL and persist its source map alongside the artifact."""
        path = self.project_path(project_id)
        result = generate_sql_project(self.load_pipeline(project_id))
        if write and result.files:
            before_hashes = self._existing_generated_hashes(path, result)
            source_map_path = path / ".sdpstudio" / "source-maps" / "generated.sql.map.json"
            if source_map_path.exists():
                try:
                    source_map = json.loads(source_map_path.read_text(encoding="utf-8"))
                    expected_hash = (source_map.get("files") or {}).get(
                        "transformations/generated.sql"
                    )
                    generated_path = path / "transformations" / "generated.sql"
                    current_hash = (
                        hashlib.sha256(generated_path.read_bytes()).hexdigest()
                        if generated_path.exists()
                        else None
                    )
                    if expected_hash and current_hash != expected_hash:
                        return result.model_copy(
                            update={
                                "files": [],
                                "problems": [
                                    *result.problems,
                                    Problem(
                                        code="SDPS-CODEGEN-DRIFT",
                                        severity="error",
                                        message="Generated SQL changed outside SDP Studio; refusing to overwrite it.",
                                        remediation="Review or restore the generated SQL, then regenerate explicitly.",
                                    ),
                                ],
                            }
                        )
                except (OSError, json.JSONDecodeError, TypeError):
                    return result.model_copy(
                        update={
                            "files": [],
                            "problems": [
                                *result.problems,
                                Problem(
                                    code="SDPS-CODEGEN-MAP",
                                    severity="error",
                                    message="Generated SQL ownership metadata is unreadable; refusing to overwrite it.",
                                ),
                            ],
                        }
                    )
            for file in result.files:
                atomic_write(path / file.path, file.content)
            source_map_payload = {
                "schemaVersion": 1,
                "mappings": [mapping.model_dump() for mapping in result.source_map],
                "files": {file.path: file.sha256 for file in result.files},
            }
            atomic_write(
                path / ".sdpstudio" / "source-maps" / "generated.sql.map.json",
                json.dumps(source_map_payload, indent=2) + "\n",
            )
            result = self._generation_diff(result, before_hashes)
        return result

    @staticmethod
    def _existing_generated_hashes(path: Path, result: Any) -> dict[str, str | None]:
        return {
            file.path: (
                hashlib.sha256((path / file.path).read_bytes()).hexdigest()
                if (path / file.path).exists()
                else None
            )
            for file in result.files
        }

    @staticmethod
    def _generation_diff(result: Any, before: dict[str, str | None]) -> Any:
        added = sum(before.get(file.path) is None for file in result.files)
        changed = sum(
            before.get(file.path) is not None and before.get(file.path) != file.sha256
            for file in result.files
        )
        unchanged = sum(before.get(file.path) == file.sha256 for file in result.files)
        return result.model_copy(
            update={
                "changed_files": [
                    file.path for file in result.files if before.get(file.path) != file.sha256
                ],
                "diff_summary": {
                    "added": added,
                    "changed": changed,
                    "unchanged": unchanged,
                },
            }
        )

    def generated_code(self, project_id: str) -> str:
        file = self.project_path(project_id) / "transformations" / "generated.py"
        return file.read_text(encoding="utf-8") if file.exists() else ""

    def code_hash(self, project_id: str) -> str:
        code = self.generated_code(project_id)
        return hashlib.sha256(code.encode("utf-8")).hexdigest() if code else ""

    def create_run(self, record: RunRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO runs(
                   id,project_id,status,mode,selected_json,command_json,code_hash,created_at,
                   started_at,finished_at,exit_code,error,pipeline_id,runtime_profile_id,run_type,
                   graph_revision_hash,git_commit,git_dirty,dirty_patch_hash,source_hash,external_run_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.id,
                    record.project_id,
                    record.status,
                    record.mode,
                    json.dumps(record.selected),
                    json.dumps(record.command),
                    record.code_hash,
                    record.created_at.isoformat(),
                    record.started_at.isoformat() if record.started_at else None,
                    record.finished_at.isoformat() if record.finished_at else None,
                    record.exit_code,
                    record.error,
                    record.pipeline_id,
                    record.runtime_profile_id,
                    record.run_type,
                    record.graph_revision_hash,
                    record.git_commit,
                    int(record.git_dirty),
                    record.dirty_patch_hash,
                    record.source_hash,
                    record.external_run_id,
                ),
            )

    def update_run(self, run_id: str, **fields: Any) -> None:
        allowed = {
            "status",
            "started_at",
            "finished_at",
            "exit_code",
            "error",
            "command_json",
            "code_hash",
            "pipeline_id",
            "runtime_profile_id",
            "run_type",
            "graph_revision_hash",
            "git_commit",
            "git_dirty",
            "dirty_patch_hash",
            "source_hash",
            "external_run_id",
            "claim_token",
            "claimed_at",
            "heartbeat_at",
        }
        updates = []
        values = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            updates.append(f"{key}=?")
            if isinstance(value, datetime):
                value = value.isoformat()
            if key == "command_json" and not isinstance(value, str):
                value = json.dumps(value)
            if key == "git_dirty":
                value = int(bool(value))
            values.append(value)
        if not updates:
            return
        values.append(run_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE runs SET {', '.join(updates)} WHERE id=?", values)

    def transition_run(self, run_id: str, status: str, **fields: Any) -> None:
        current = str(self.get_run(run_id)["status"])
        if not is_valid_run_transition(current, status):
            raise ValueError(f"Invalid run state transition: {current} -> {status}")
        self.update_run(run_id, status=status, **fields)

    def claim_run(self, worker_id: str, lease_seconds: int = 60) -> dict[str, Any] | None:
        """Atomically claim one queued run, reclaiming expired leases."""
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        now = datetime.now(UTC)
        cutoff_iso = datetime.fromtimestamp(
            now.timestamp() - max(1, lease_seconds), UTC
        ).isoformat()
        token = f"{worker_id}:{new_ulid()}"
        with self._connect() as conn:
            claim_query = (
                "SELECT id FROM runs WHERE status='queued' AND "
                "(claim_token IS NULL OR heartbeat_at IS NULL OR heartbeat_at<?) "
                "ORDER BY created_at LIMIT 1"
            )
            if self.uses_postgres:
                # Keep the row lock until the claim update commits so multiple
                # worker processes cannot select the same queued run.
                claim_query += " FOR UPDATE SKIP LOCKED"
            candidate = conn.execute(claim_query, (cutoff_iso,)).fetchone()
            if candidate is None:
                return None
            updated = conn.execute(
                "UPDATE runs SET claim_token=?,claimed_at=?,heartbeat_at=? "
                "WHERE id=? AND status='queued' AND "
                "(claim_token IS NULL OR heartbeat_at IS NULL OR heartbeat_at<?)",
                (token, now.isoformat(), now.isoformat(), candidate["id"], cutoff_iso),
            ).rowcount
            if updated != 1:
                return None
            row = conn.execute("SELECT * FROM runs WHERE id=?", (candidate["id"],)).fetchone()
            return dict(row) if row else None

    def heartbeat_run(self, run_id: str, claim_token: str) -> bool:
        if not claim_token:
            return False
        with self._connect() as conn:
            return (
                conn.execute(
                    "UPDATE runs SET heartbeat_at=? WHERE id=? AND claim_token=? AND status='queued'",
                    (datetime.now(UTC).isoformat(), run_id, claim_token),
                ).rowcount
                == 1
            )

    def release_run_claim(self, run_id: str, claim_token: str) -> bool:
        with self._connect() as conn:
            return (
                conn.execute(
                    "UPDATE runs SET claim_token=NULL,claimed_at=NULL,heartbeat_at=NULL "
                    "WHERE id=? AND claim_token=?",
                    (run_id, claim_token),
                ).rowcount
                == 1
            )

    def reconcile_non_terminal_runs(self) -> list[str]:
        """Mark in-memory/local submissions as lost after a server restart.

        External adapters can later replace this conservative fallback with a status
        probe; claiming success or failure without that probe would violate the run
        contract.
        """
        terminal = {"succeeded", "failed", "cancelled", "validation_failed", "lost"}
        with self._connect() as conn:
            rows = conn.execute("SELECT id,status FROM runs").fetchall()
            lost = [row["id"] for row in rows if row["status"] not in terminal]
            for run_id in lost:
                conn.execute(
                    "UPDATE runs SET status=?,finished_at=?,error=? WHERE id=?",
                    ("lost", utc_now(), "Run could not be reconciled after server restart", run_id),
                )
        for run_id in lost:
            self.add_run_event(
                run_id,
                "status",
                "Run marked lost during startup reconciliation",
                {"code": "SDPS-RUN-LOST"},
            )
        return lost

    def add_run_event(
        self, run_id: str, kind: str, message: str, data: dict[str, Any] | None = None
    ) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq),0)+1 AS seq FROM run_events WHERE run_id=?", (run_id,)
            ).fetchone()
            seq = int(row["seq"])
            conn.execute(
                "INSERT INTO run_events(run_id,seq,ts,kind,message,data_json) VALUES(?,?,?,?,?,?)",
                (run_id, seq, utc_now(), kind, message, json.dumps(data or {})),
            )
        return seq

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError(run_id)
        item = dict(row)
        item["selected"] = json.loads(item.pop("selected_json"))
        item["command"] = json.loads(item.pop("command_json"))
        return item

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs WHERE project_id=? ORDER BY created_at DESC LIMIT 200",
                (project_id,),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["selected"] = json.loads(item.pop("selected_json"))
            item["command"] = json.loads(item.pop("command_json"))
            items.append(item)
        return items

    def run_events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM run_events WHERE run_id=? AND seq>? ORDER BY seq", (run_id, after)
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["data"] = json.loads(item.pop("data_json"))
            items.append(item)
        return items

    def save_node_snapshot(
        self,
        run_id: str,
        node_id: str,
        *,
        schema: list[dict[str, Any]] | None = None,
        profile: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        plan_artifact_id: str | None = None,
    ) -> dict[str, Any]:
        snapshot_id = new_ulid()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO node_snapshots(id,run_id,node_id,schema_json,profile_json,metrics_json,plan_artifact_id) VALUES(?,?,?,?,?,?,?)",
                (
                    snapshot_id,
                    run_id,
                    node_id,
                    json.dumps(schema) if schema is not None else None,
                    json.dumps(profile) if profile is not None else None,
                    json.dumps(metrics) if metrics is not None else None,
                    plan_artifact_id,
                ),
            )
        return self.get_node_snapshots(run_id)[-1]

    def get_node_snapshots(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM node_snapshots WHERE run_id=? ORDER BY id", (run_id,)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            for key in ("schema_json", "profile_json", "metrics_json"):
                raw = item.pop(key)
                item[key.removesuffix("_json")] = json.loads(raw) if raw is not None else None
            result.append(item)
        return result
