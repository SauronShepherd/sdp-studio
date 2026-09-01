import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sdpstudio_core.models import RunRecord
from sdpstudio_server.storage import DataStore


def test_run_record_supports_spec_states():
    record = RunRecord(project_id="project", status="collecting_artifacts")
    assert record.status == "collecting_artifacts"
    assert RunRecord(project_id="project", status="lost").status == "lost"


def test_startup_reconciliation_marks_non_terminal_runs_lost(tmp_path):
    store = DataStore(tmp_path)
    project = store.create_project("reconcile")
    record = RunRecord(project_id=project["id"], status="running", created_at=datetime.now(UTC))
    store.create_run(record)

    assert store.reconcile_non_terminal_runs() == [record.id]
    run = store.get_run(record.id)
    assert run["status"] == "lost"
    assert "server restart" in run["error"]
    assert store.run_events(record.id)[-1]["data"]["code"] == "SDPS-RUN-LOST"


def test_run_transition_guard_rejects_terminal_state_reversal(tmp_path):
    store = DataStore(tmp_path)
    project = store.create_project("transition")
    record = RunRecord(project_id=project["id"], status="created")
    store.create_run(record)
    store.transition_run(record.id, "queued")
    store.transition_run(record.id, "failed", error="expected")
    with pytest.raises(ValueError, match="Invalid run state transition"):
        store.transition_run(record.id, "running")


def test_run_reproducibility_metadata_is_persisted(tmp_path):
    store = DataStore(tmp_path)
    project = store.create_project("metadata")
    record = RunRecord(
        project_id=project["id"],
        pipeline_id="pipeline-1",
        runtime_profile_id="runtime-1",
        graph_revision_hash="a" * 64,
        source_hash="b" * 64,
        git_commit="c" * 40,
        git_dirty=True,
        dirty_patch_hash="d" * 64,
        external_run_id="external-1",
    )
    store.create_run(record)
    saved = store.get_run(record.id)
    assert saved["pipeline_id"] == "pipeline-1"
    assert saved["runtime_profile_id"] == "runtime-1"
    assert saved["graph_revision_hash"] == "a" * 64
    assert saved["git_dirty"] in (True, 1)
    assert saved["external_run_id"] == "external-1"


def test_run_claim_is_exclusive_and_heartbeat_requires_ownership(tmp_path):
    store = DataStore(tmp_path)
    project = store.create_project("claims")
    record = RunRecord(project_id=project["id"], status="queued")
    store.create_run(record)
    claimed = store.claim_run("worker-a")
    assert claimed and claimed["id"] == record.id
    assert store.claim_run("worker-b") is None
    assert store.heartbeat_run(record.id, claimed["claim_token"]) is True
    assert store.heartbeat_run(record.id, "wrong-token") is False
    assert store.release_run_claim(record.id, claimed["claim_token"]) is True
    assert store.claim_run("worker-b") is not None


def test_live_store_bootstraps_spec_metadata_tables(tmp_path):
    store = DataStore(tmp_path)
    with store._connect() as conn:
        run_columns = {row["name"] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert {
        "graph_revision_hash",
        "git_dirty",
        "source_hash",
        "claim_token",
        "heartbeat_at",
    } <= run_columns
    assert {"repositories", "documents", "local_revisions", "artifacts", "node_snapshots"} <= tables


def test_node_schema_snapshots_are_persisted_per_run(tmp_path):
    store = DataStore(tmp_path)
    project = store.create_project("snapshots")
    record = RunRecord(project_id=project["id"], status="created")
    store.create_run(record)
    saved = store.save_node_snapshot(
        record.id,
        "node-1",
        schema=[{"name": "id", "type": "integer"}],
        profile={"row_count": 2},
        metrics={"duration_ms": 10},
    )
    assert saved["node_id"] == "node-1"
    assert store.get_node_snapshots(record.id)[0]["schema"][0]["name"] == "id"


def test_local_runtime_reconciles_durable_orphan_marker(tmp_path):
    import json

    from sdpstudio_runners.local import LocalRuntime

    store = DataStore(tmp_path)
    project = store.create_project("orphan")
    record = RunRecord(project_id=project["id"])
    store.create_run(record)
    store.transition_run(record.id, "queued")
    store.transition_run(record.id, "preparing")
    marker = (
        Path(project["path"])
        / ".sdpstudio"
        / "runtime"
        / "run-artifacts"
        / record.id
        / "process.json"
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"run_id": record.id, "pid": 99999999}), encoding="utf-8")
    assert LocalRuntime(store).reconcile_orphaned_processes() == [record.id]
    assert store.get_run(record.id)["status"] == "lost"
    assert not marker.exists()


def test_kubernetes_terminal_pod_reconciles_run_state(tmp_path, monkeypatch):
    from sdpstudio_runners.local import LocalRuntime

    store = DataStore(tmp_path)
    project = store.create_project("k8s-status")
    record = RunRecord(project_id=project["id"], status="created")
    store.create_run(record)
    for status in ("queued", "preparing", "validating", "submitting", "running"):
        store.transition_run(record.id, status)
    artifact = Path(project["path"]) / ".sdpstudio" / "runtime" / "run-artifacts" / record.id
    artifact.mkdir(parents=True, exist_ok=True)
    (artifact / "run-snapshot.json").write_text(
        json.dumps({"runtime_profile": {"adapter": "kubernetes", "config": {"namespace": "data"}}}),
        encoding="utf-8",
    )
    runtime = LocalRuntime(store)
    monkeypatch.setattr(
        runtime,
        "_kubectl",
        lambda _command: asyncio.sleep(
            0,
            result={
                "ok": True,
                "output": json.dumps({"status": {"phase": "Succeeded"}}),
                "exit_code": 0,
            },
        ),
    )
    result = asyncio.run(runtime.kubernetes_status(record.id))
    assert result["lifecycle_status"] == "succeeded"
    assert store.get_run(record.id)["status"] == "succeeded"
