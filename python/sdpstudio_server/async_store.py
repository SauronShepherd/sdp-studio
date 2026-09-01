"""Async boundary for the synchronous compatibility store.

The local SQLite/PostgreSQL store remains deliberately small and DB-API based
for the 0.1 migration path. Route handlers use this facade for blocking store
operations so database work is moved off the event loop while the persistence
implementation is migrated behind the service interfaces described by the
specification.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from sdpstudio_core.ids import new_ulid
from sqlalchemy import text

from .compatibility_store import CompatibilityStoreBoundary
from .database import create_engine, sqlite_url
from .runtime_profile_service import validate_runtime_profile
from .secrets import EncryptedSecret, SecretVault


class AsyncStore:
    def __init__(self, store: Any) -> None:
        self._compatibility = CompatibilityStoreBoundary(store)
        # SQLAlchemy's concrete async engine is optional for PostgreSQL and is
        # created only for local SQLite stores. Keep the boundary explicitly
        # dynamic because the compatibility store may not expose db_path.
        self._engine: Any = None
        self._engine_loop_id: int | None = None
        if hasattr(store, "db_path") and not getattr(store, "uses_postgres", False):
            self._engine = create_engine(sqlite_url(store.db_path))

    async def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        sqlite_methods = {
            "health_check",
            "list_projects",
            "get_project_row",
            "get_run",
            "list_runs",
            "run_events",
            "get_node_snapshots",
            "append_audit_event",
            "save_node_snapshot",
            "list_runtime_profiles",
            "get_runtime_profile",
            "create_runtime_profile",
            "update_runtime_profile",
            "delete_runtime_profile",
            "list_schedules",
            "get_schedule",
            "create_schedule",
            "update_schedule",
            "delete_schedule",
            "claim_schedule",
            "append_collaboration_event",
            "collaboration_events",
            "collaboration_snapshot",
            "save_collaboration_snapshot",
            "compact_collaboration_events",
            "list_users",
            "list_audit_events",
            "save_user",
            "put_secret",
            "rotate_secrets",
            "delete_secret",
            "resolve_secret",
        }
        current_loop_id = id(asyncio.get_running_loop())
        # AsyncEngine/aiosqlite connections are loop-bound. TestClient and
        # other short-lived embedders may invoke one app from multiple loops;
        # keep those calls on the compatibility thread path rather than
        # allowing a worker callback to target a loop that has already closed.
        use_sqlite_engine = (
            self._engine is not None
            and method in sqlite_methods
            and (self._engine_loop_id is None or self._engine_loop_id == current_loop_id)
        )
        if use_sqlite_engine:
            self._engine_loop_id = current_loop_id
            try:
                return await self._query_sqlite(method, *args, **kwargs)
            finally:
                # SQLite uses NullPool and each operation owns its aiosqlite
                # worker connection. Dispose promptly so callers that create
                # short-lived app instances without a lifespan context cannot
                # leave worker callbacks attached to a closed event loop.
                await self._engine.dispose()
        return await self._compatibility.call(method, *args, **kwargs)

    async def _query_sqlite(self, method: str, *args: Any, **kwargs: Any) -> Any:
        if method == "health_check":
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        if method == "list_projects":
            prefix = str(kwargs.get("prefix", args[0] if args else ""))
            query = "SELECT * FROM projects WHERE name LIKE :prefix ORDER BY created_at"
            parameters = {"prefix": f"{prefix}%"}
            async with self._engine.connect() as connection:
                rows = (await connection.execute(text(query), parameters)).mappings().all()
            return [dict(row) for row in rows]
        if method == "get_run":
            run_id = str(args[0] if args else kwargs["run_id"])
            query, parameters = "SELECT * FROM runs WHERE id = :run_id", {"run_id": run_id}
            async with self._engine.connect() as connection:
                row = (await connection.execute(text(query), parameters)).mappings().first()
            if row is None:
                raise KeyError(run_id)
            item = dict(row)
            item["selected"] = json.loads(item.pop("selected_json"))
            item["command"] = json.loads(item.pop("command_json"))
            return item
        if method == "list_runs":
            project_id = str(args[0] if args else kwargs["project_id"])
            query = "SELECT * FROM runs WHERE project_id = :project_id ORDER BY created_at DESC LIMIT 200"
            async with self._engine.connect() as connection:
                rows = (
                    (await connection.execute(text(query), {"project_id": project_id}))
                    .mappings()
                    .all()
                )
            result = []
            for row in rows:
                item = dict(row)
                item["selected"] = json.loads(item.pop("selected_json"))
                item["command"] = json.loads(item.pop("command_json"))
                result.append(item)
            return result
        if method == "run_events":
            run_id = str(args[0] if args else kwargs["run_id"])
            after = int(kwargs.get("after", args[1] if len(args) > 1 else 0))
            query = "SELECT * FROM run_events WHERE run_id = :run_id AND seq > :after ORDER BY seq"
            async with self._engine.connect() as connection:
                rows = (
                    (await connection.execute(text(query), {"run_id": run_id, "after": after}))
                    .mappings()
                    .all()
                )
            result = []
            for row in rows:
                item = dict(row)
                item["data"] = json.loads(item.pop("data_json"))
                result.append(item)
            return result
        if method == "get_node_snapshots":
            run_id = str(args[0] if args else kwargs["run_id"])
            async with self._engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            text("SELECT * FROM node_snapshots WHERE run_id = :run_id ORDER BY id"),
                            {"run_id": run_id},
                        )
                    )
                    .mappings()
                    .all()
                )
            result = []
            for row in rows:
                item = dict(row)
                for key in ("schema_json", "profile_json", "metrics_json"):
                    raw = item.pop(key)
                    item[key.removesuffix("_json")] = json.loads(raw) if raw is not None else None
                result.append(item)
            return result
        if method == "append_audit_event":
            actor, action, resource_type, resource_id = args[:4]
            metadata = args[4] if len(args) > 4 else kwargs.get("metadata")
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO audit_events "
                        "(id,actor,action,resource_type,resource_id,metadata_json,created_at) "
                        "VALUES (:id,:actor,:action,:resource_type,:resource_id,:metadata,:created_at)"
                    ),
                    {
                        "id": new_ulid(),
                        "actor": str(actor),
                        "action": str(action),
                        "resource_type": str(resource_type),
                        "resource_id": resource_id,
                        "metadata": json.dumps(metadata or {}, sort_keys=True),
                        "created_at": datetime.now(UTC).isoformat(),
                    },
                )
            return None
        if method == "save_node_snapshot":
            run_id, node_id = args[:2]
            schema = kwargs.get("schema")
            profile = kwargs.get("profile")
            metrics = kwargs.get("metrics")
            plan_artifact_id = kwargs.get("plan_artifact_id")
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO node_snapshots "
                        "(id,run_id,node_id,schema_json,profile_json,metrics_json,plan_artifact_id) "
                        "VALUES (:id,:run_id,:node_id,:schema,:profile,:metrics,:plan_artifact_id)"
                    ),
                    {
                        "id": new_ulid(),
                        "run_id": run_id,
                        "node_id": node_id,
                        "schema": json.dumps(schema) if schema is not None else None,
                        "profile": json.dumps(profile) if profile is not None else None,
                        "metrics": json.dumps(metrics) if metrics is not None else None,
                        "plan_artifact_id": plan_artifact_id,
                    },
                )
            snapshots = await self._query_sqlite("get_node_snapshots", run_id)
            return snapshots[-1]
        if method == "resolve_secret":
            return await asyncio.to_thread(self._compatibility.call, "resolve_secret", str(args[0]))
        if method == "list_runtime_profiles":
            async with self._engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            text("SELECT * FROM runtime_profiles ORDER BY created_at")
                        )
                    )
                    .mappings()
                    .all()
                )
            return [self._profile_mapping(row) for row in rows]
        if method == "get_runtime_profile":
            profile_id = str(args[0] if args else kwargs["profile_id"])
            async with self._engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text("SELECT * FROM runtime_profiles WHERE id = :id"),
                            {"id": profile_id},
                        )
                    )
                    .mappings()
                    .first()
                )
            if row is None:
                raise KeyError(profile_id)
            return self._profile_mapping(row)
        if method == "create_runtime_profile":
            name, adapter, config = args[:3]
            validate_runtime_profile(adapter, config)
            profile_id = new_ulid()
            protected = bool(kwargs.get("is_protected", False))
            now = datetime.now(UTC).isoformat()
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO runtime_profiles "
                        "(id,name,adapter,config_json,is_protected,created_at,updated_at) "
                        "VALUES (:id,:name,:adapter,:config,:protected,:created_at,:updated_at)"
                    ),
                    {
                        "id": profile_id,
                        "name": name,
                        "adapter": adapter,
                        "config": json.dumps(config),
                        "protected": int(protected),
                        "created_at": now,
                        "updated_at": now,
                    },
                )
            return await self._query_sqlite("get_runtime_profile", profile_id)
        if method == "update_runtime_profile":
            profile_id = str(args[0])
            current = await self._query_sqlite("get_runtime_profile", profile_id)
            name = kwargs.get("name") or current["name"]
            adapter = kwargs.get("adapter") or current["adapter"]
            config = kwargs.get("config") if kwargs.get("config") is not None else current["config"]
            if not isinstance(config, dict):
                config = {}
            protected = (
                bool(kwargs["is_protected"])
                if kwargs.get("is_protected") is not None
                else bool(current.get("is_protected"))
            )
            validate_runtime_profile(adapter, config)
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE runtime_profiles SET name=:name,adapter=:adapter,"
                        "config_json=:config,is_protected=:protected,updated_at=:updated_at WHERE id=:id"
                    ),
                    {
                        "id": profile_id,
                        "name": name,
                        "adapter": adapter,
                        "config": json.dumps(config),
                        "protected": int(protected),
                        "updated_at": datetime.now(UTC).isoformat(),
                    },
                )
            return await self._query_sqlite("get_runtime_profile", profile_id)
        if method == "delete_runtime_profile":
            profile_id = str(args[0])
            current = await self._query_sqlite("get_runtime_profile", profile_id)
            if current["adapter"] == "local":
                async with self._engine.connect() as connection:
                    count = (
                        await connection.execute(
                            text("SELECT COUNT(*) FROM runtime_profiles WHERE adapter='local'")
                        )
                    ).scalar_one()
                if count <= 1:
                    raise ValueError("Cannot delete the last local runtime profile")
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    text("DELETE FROM runtime_profiles WHERE id=:id"), {"id": profile_id}
                )
            if result.rowcount == 0:
                raise KeyError(profile_id)
            return None
        if method == "list_schedules":
            project_id = str(args[0] if args else kwargs["project_id"])
            async with self._engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM schedules WHERE project_id=:project_id ORDER BY created_at"
                            ),
                            {"project_id": project_id},
                        )
                    )
                    .mappings()
                    .all()
                )
            return [self._schedule_mapping(row) for row in rows]
        if method == "get_schedule":
            schedule_id = str(args[0] if args else kwargs["schedule_id"])
            async with self._engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text("SELECT * FROM schedules WHERE id=:id"), {"id": schedule_id}
                        )
                    )
                    .mappings()
                    .first()
                )
            if row is None:
                raise KeyError(schedule_id)
            return self._schedule_mapping(row)
        if method == "create_schedule":
            values = {**kwargs}
            project_id = args[0]
            name = str(values.pop("name", args[1] if len(args) > 1 else "schedule"))
            cron = str(values.get("cron", args[2] if len(args) > 2 else ""))
            timezone = str(values.get("timezone", "UTC"))
            mode = str(values.get("mode", "incremental"))
            concurrency = str(values.get("concurrency_policy", "skip"))
            missed = str(values.get("missed_run_policy", "skip"))
            if len(cron.split()) != 5:
                raise ValueError("Schedule cron must contain exactly five fields")
            if mode not in {"incremental", "refresh", "full-refresh-all"}:
                raise ValueError("Unsupported schedule mode")
            if concurrency not in {"skip", "forbid", "replace"}:
                raise ValueError("Unsupported schedule concurrency policy")
            if missed not in {"skip", "run_once"}:
                raise ValueError("Unsupported missed-run policy")
            schedule_id = new_ulid()
            now = datetime.now(UTC).isoformat()
            async with self._engine.begin() as connection:
                project = await connection.execute(
                    text("SELECT 1 FROM projects WHERE id=:id"), {"id": project_id}
                )
                if project.first() is None:
                    raise KeyError(project_id)
                await connection.execute(
                    text(
                        "INSERT INTO schedules "
                        "(id,project_id,name,cron,timezone,enabled,runtime_profile_id,mode,"
                        "concurrency_policy,missed_run_policy,created_at,updated_at) "
                        "VALUES (:id,:project_id,:name,:cron,:timezone,:enabled,:profile,:mode,"
                        ":concurrency,:missed,:created_at,:updated_at)"
                    ),
                    {
                        "id": schedule_id,
                        "project_id": project_id,
                        "name": name,
                        "cron": cron,
                        "timezone": timezone,
                        "enabled": int(values.get("enabled", True)),
                        "profile": values.get("runtime_profile_id"),
                        "mode": mode,
                        "concurrency": concurrency,
                        "missed": missed,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
            return await self._query_sqlite("get_schedule", schedule_id)
        if method == "update_schedule":
            schedule_id, updates = args[:2]
            if not isinstance(updates, dict) or not updates:
                raise ValueError("Schedule update requires at least one field")
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
            assignments = [f"{key}=:{key}" for key in changes]
            changes.update({"id": schedule_id, "updated": datetime.now(UTC).isoformat()})
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    text(
                        f"UPDATE schedules SET {', '.join(assignments)},updated_at=:updated WHERE id=:id"
                    ),
                    {
                        key: int(value) if key == "enabled" else value
                        for key, value in changes.items()
                    },
                )
            if result.rowcount == 0:
                raise KeyError(schedule_id)
            return await self._query_sqlite("get_schedule", schedule_id)
        if method == "delete_schedule":
            schedule_id = str(args[0])
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    text("DELETE FROM schedules WHERE id=:id"), {"id": schedule_id}
                )
            if result.rowcount == 0:
                raise KeyError(schedule_id)
            return None
        if method == "claim_schedule":
            schedule_id, marker = args[:2]
            now = datetime.now(UTC).isoformat()
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    text(
                        "UPDATE schedules SET last_claim_marker=:marker,claimed_at=:now,updated_at=:now "
                        "WHERE id=:id AND enabled=1 AND "
                        "(last_claim_marker IS NULL OR last_claim_marker<>:marker)"
                    ),
                    {"id": schedule_id, "marker": marker, "now": now},
                )
            return result.rowcount == 1
        if method == "collaboration_events":
            project_id = str(args[0])
            after = int(kwargs.get("after", args[1] if len(args) > 1 else 0))
            async with self._engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            text(
                                "SELECT seq,event_json,created_at FROM collaboration_events "
                                "WHERE project_id=:project_id AND seq>:after ORDER BY seq"
                            ),
                            {"project_id": project_id, "after": after},
                        )
                    )
                    .mappings()
                    .all()
                )
            return [
                {
                    "project_id": project_id,
                    "seq": int(row["seq"]),
                    **json.loads(row["event_json"]),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        if method == "collaboration_snapshot":
            project_id = str(args[0])
            async with self._engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT project_id,seq,document_json,created_at "
                                "FROM collaboration_snapshots WHERE project_id=:project_id"
                            ),
                            {"project_id": project_id},
                        )
                    )
                    .mappings()
                    .first()
                )
            if row is None:
                return None
            return {
                "project_id": row["project_id"],
                "seq": int(row["seq"]),
                "document": json.loads(row["document_json"]),
                "created_at": row["created_at"],
            }
        if method == "append_collaboration_event":
            project_id, event = args[:2]
            async with self._engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT COALESCE(MAX(seq),0)+1 AS seq FROM ("
                                "SELECT seq FROM collaboration_events WHERE project_id=:project_id "
                                "UNION ALL SELECT seq FROM collaboration_snapshots WHERE project_id=:project_id)"
                            ),
                            {"project_id": project_id},
                        )
                    )
                    .mappings()
                    .first()
                )
                seq = int(row["seq"])
                now = datetime.now(UTC).isoformat()
                await connection.execute(
                    text(
                        "INSERT INTO collaboration_events(project_id,seq,event_json,created_at) "
                        "VALUES (:project_id,:seq,:event,:created_at)"
                    ),
                    {
                        "project_id": project_id,
                        "seq": seq,
                        "event": json.dumps(event, sort_keys=True),
                        "created_at": now,
                    },
                )
                if seq % 100 == 0:
                    rows = (
                        (
                            await connection.execute(
                                text(
                                    "SELECT seq,event_json FROM collaboration_events "
                                    "WHERE project_id=:project_id ORDER BY seq"
                                ),
                                {"project_id": project_id},
                            )
                        )
                        .mappings()
                        .all()
                    )
                    updates = [
                        json.loads(row["event_json"])
                        for row in rows
                        if json.loads(row["event_json"]).get("type") == "y_update"
                    ]
                    snapshot = {"format": "yjs-update-bundle", "updates": updates}
                    await connection.execute(
                        text(
                            "INSERT INTO collaboration_snapshots(project_id,seq,document_json,created_at) "
                            "VALUES (:project_id,:seq,:document,:created_at) "
                            "ON CONFLICT(project_id) DO UPDATE SET seq=excluded.seq,"
                            "document_json=excluded.document_json,created_at=excluded.created_at"
                        ),
                        {
                            "project_id": project_id,
                            "seq": seq,
                            "document": json.dumps(snapshot, sort_keys=True),
                            "created_at": now,
                        },
                    )
                    await connection.execute(
                        text(
                            "DELETE FROM collaboration_events "
                            "WHERE project_id=:project_id AND seq<=:seq"
                        ),
                        {"project_id": project_id, "seq": seq},
                    )
            return {"project_id": project_id, "seq": seq, **event, "created_at": now}
        if method == "save_collaboration_snapshot":
            project_id, document = args[:2]
            snapshot_seq: int | None = kwargs.get("seq")
            if snapshot_seq is not None:
                snapshot_seq = int(snapshot_seq)
            if snapshot_seq is None:
                events = await self._query_sqlite("collaboration_events", project_id)
                snapshot_seq = int(events[-1]["seq"]) if events else 0
            now = datetime.now(UTC).isoformat()
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO collaboration_snapshots(project_id,seq,document_json,created_at) "
                        "VALUES (:project_id,:seq,:document,:created_at) "
                        "ON CONFLICT(project_id) DO UPDATE SET seq=excluded.seq,"
                        "document_json=excluded.document_json,created_at=excluded.created_at"
                    ),
                    {
                        "project_id": project_id,
                        "seq": snapshot_seq,
                        "document": json.dumps(document, sort_keys=True),
                        "created_at": now,
                    },
                )
            return {
                "project_id": project_id,
                "seq": snapshot_seq,
                "document": document,
                "created_at": now,
            }
        if method == "compact_collaboration_events":
            project_id, keep_after = args[:2]
            snapshot = await self._query_sqlite("collaboration_snapshot", project_id)
            if snapshot is None or int(snapshot["seq"]) < int(keep_after):
                return 0
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    text(
                        "DELETE FROM collaboration_events WHERE project_id=:project_id AND seq<:keep_after"
                    ),
                    {"project_id": project_id, "keep_after": keep_after},
                )
            return int(result.rowcount)
        if method == "list_users":
            async with self._engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            text(
                                "SELECT username,role,password_hash,created_at,updated_at FROM users ORDER BY username"
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
            return [dict(row) for row in rows]
        if method == "list_audit_events":
            limit = max(1, min(int(args[0] if args else kwargs.get("limit", 100)), 500))
            async with self._engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            text(
                                "SELECT id,actor,action,resource_type,resource_id,metadata_json,created_at "
                                "FROM audit_events ORDER BY created_at DESC,id DESC LIMIT :limit"
                            ),
                            {"limit": limit},
                        )
                    )
                    .mappings()
                    .all()
                )
            result = []
            for row in rows:
                item = dict(row)
                item["metadata"] = json.loads(item.pop("metadata_json"))
                result.append(item)
            return result
        if method == "save_user":
            username, role, password_hash = args[:3]
            now = datetime.now(UTC).isoformat()
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO users(username,role,password_hash,created_at,updated_at) "
                        "VALUES (:username,:role,:password_hash,:created_at,:updated_at) "
                        "ON CONFLICT(username) DO UPDATE SET role=excluded.role,"
                        "password_hash=excluded.password_hash,updated_at=excluded.updated_at"
                    ),
                    {
                        "username": username,
                        "role": role,
                        "password_hash": password_hash,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
            users = await self._query_sqlite("list_users")
            return next(item for item in users if item["username"] == username)
        if method == "put_secret":
            name, value = args[:2]
            vault = SecretVault.from_environment()
            encrypted = vault.encrypt(value, associated_data=name)
            now = datetime.now(UTC).isoformat()
            async with self._engine.begin() as connection:
                existing = (
                    (
                        await connection.execute(
                            text("SELECT id FROM secrets WHERE name=:name"), {"name": name}
                        )
                    )
                    .mappings()
                    .first()
                )
                secret_id = existing["id"] if existing else new_ulid()
                if existing:
                    await connection.execute(
                        text(
                            "UPDATE secrets SET ciphertext=:ciphertext,key_id=:key_id,updated_at=:updated "
                            "WHERE id=:id"
                        ),
                        {
                            "ciphertext": encrypted.ciphertext,
                            "key_id": encrypted.key_id,
                            "updated": now,
                            "id": secret_id,
                        },
                    )
                else:
                    await connection.execute(
                        text(
                            "INSERT INTO secrets(id,name,ciphertext,key_id,created_at,updated_at) "
                            "VALUES (:id,:name,:ciphertext,:key_id,:created,:updated)"
                        ),
                        {
                            "id": secret_id,
                            "name": name,
                            "ciphertext": encrypted.ciphertext,
                            "key_id": encrypted.key_id,
                            "created": now,
                            "updated": now,
                        },
                    )
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT id,name,key_id,created_at,updated_at FROM secrets WHERE id=:id"
                            ),
                            {"id": secret_id},
                        )
                    )
                    .mappings()
                    .first()
                )
            return dict(row)
        if method == "rotate_secrets":
            vault = SecretVault.from_environment()
            now = datetime.now(UTC).isoformat()
            rotated = 0
            async with self._engine.begin() as connection:
                rows = (
                    (
                        await connection.execute(
                            text("SELECT id,name,ciphertext,key_id FROM secrets ORDER BY name")
                        )
                    )
                    .mappings()
                    .all()
                )
                for row in rows:
                    encrypted = vault.rotate(
                        EncryptedSecret(str(row["ciphertext"]), str(row["key_id"])),
                        associated_data=str(row["name"]),
                    )
                    await connection.execute(
                        text(
                            "UPDATE secrets SET ciphertext=:ciphertext,key_id=:key_id,updated_at=:updated "
                            "WHERE id=:id"
                        ),
                        {
                            "ciphertext": encrypted.ciphertext,
                            "key_id": encrypted.key_id,
                            "updated": now,
                            "id": row["id"],
                        },
                    )
                    rotated += 1
            return {"rotated": rotated, "key_id": vault.key_id}
        if method == "delete_secret":
            secret_id = str(args[0])
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    text("DELETE FROM secrets WHERE id=:id"), {"id": secret_id}
                )
            if result.rowcount == 0:
                raise KeyError(secret_id)
            return None

        project_id = str(args[0] if args else kwargs["project_id"])
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM projects WHERE id = :project_id"),
                        {"project_id": project_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise KeyError(f"Project not found: {project_id}")
        return dict(row)

    @staticmethod
    def _profile_mapping(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["config"] = json.loads(item.pop("config_json"))
        return item

    @staticmethod
    def _schedule_mapping(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        return item

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine_loop_id = None

    @property
    def sync_store(self) -> Any:
        """Expose the underlying store only to non-route lifecycle code."""
        return self._compatibility.sync_store
