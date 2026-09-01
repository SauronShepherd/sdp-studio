import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sdpstudio_core.models import Edge, Node, PipelineDocument, PortRef, RunRecord
from sdpstudio_server.app import create_app
from sdpstudio_server.catalog import local_catalog
from sdpstudio_server.storage import DataStore


def test_persisted_pipeline_requires_explicit_schema_version(tmp_path: Path):
    store = DataStore(tmp_path)
    project = store.create_project("schema-required")
    path = Path(project["path"]) / ".sdpstudio" / "pipelines" / "main.sdpstudio.yaml"
    path.write_text("pipelineId: p\nname: broken\nnodes: []\nedges: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SDPS-SCHEMA-001"):
        store.load_pipeline(project["id"])


@pytest.mark.parametrize("status", ["validation_failed", "lost"])
def test_run_websocket_emits_eof_for_all_terminal_failure_states(tmp_path: Path, status: str):
    app = create_app(tmp_path)
    project = app.state.store.create_project("terminal-ws")
    record = RunRecord(project_id=project["id"], status=status)
    app.state.store.create_run(record)

    with TestClient(app).websocket_connect(f"/ws/runs/{record.id}") as socket:
        event = socket.receive_json()

    assert event == {
        "kind": "eof",
        "type": "run.eof",
        "status": status,
        "seq": 1,
    }


def test_project_api_generate_history_and_git(tmp_path: Path):
    app = create_app(tmp_path)
    client = TestClient(app)
    created = client.post("/api/projects", json={"name": "orders"})
    assert created.status_code == 200
    project_id = created.json()["id"]

    source = Node(type="source.table", config={"table": "raw.orders", "streaming": False})
    filt = Node(type="transform.filter", config={"expression": "amount > 10"})
    out = Node(type="dataset.materialized_view", config={"name": "large_orders"})
    doc = PipelineDocument(
        name="orders",
        nodes=[source, filt, out],
        edges=[
            Edge(**{"from": PortRef(node=source.id), "to": PortRef(node=filt.id, port="in")}),
            Edge(**{"from": PortRef(node=filt.id), "to": PortRef(node=out.id, port="in")}),
        ],
    )
    saved = client.put(f"/api/projects/{project_id}/pipeline", json=doc.model_dump(by_alias=True))
    assert saved.status_code == 200
    validation = client.post(f"/api/projects/{project_id}/validate").json()
    assert validation["valid"] is True

    generated = client.post(f"/api/projects/{project_id}/generate")
    assert generated.status_code == 200
    generation_payload = generated.json()
    assert generation_payload["changed_files"]
    assert sum(generation_payload["diff_summary"].values()) >= 1
    unchanged = client.post(f"/api/projects/{project_id}/generate")
    assert unchanged.status_code == 200
    assert unchanged.json()["diff_summary"]["unchanged"] >= 1
    code = client.get(f"/api/projects/{project_id}/code").json()["content"]
    assert "large_orders" in code
    assert "amount > 10" in code
    sql = client.post(f"/api/projects/{project_id}/generate-sql")
    assert sql.status_code == 200
    assert "CREATE OR REPLACE MATERIALIZED VIEW large_orders" in sql.json()["files"][0]["content"]
    assert (
        app.state.store.project_path(project_id)
        / ".sdpstudio"
        / "source-maps"
        / "generated.sql.map.json"
    ).exists()

    history = client.get(f"/api/projects/{project_id}/history").json()
    assert len(history) >= 1
    git_init = client.post(f"/api/projects/{project_id}/git/init")
    assert git_init.status_code == 200
    staged = client.post(f"/api/projects/{project_id}/git/stage")
    assert staged.status_code == 200
    committed = client.post(
        f"/api/projects/{project_id}/git/commit", json={"message": "Initial visual pipeline"}
    )
    assert committed.status_code == 200
    assert committed.json()["initialized"] is True
    graph_diff = client.get(f"/api/projects/{project_id}/git/graph-diff?left=HEAD&right=HEAD")
    assert graph_diff.status_code == 200
    assert graph_diff.json()["diff"]["changed_nodes"] == []
    created_tag = client.post(
        f"/api/projects/{project_id}/git/tags", json={"name": "v0.1.0", "message": "release"}
    )
    assert created_tag.status_code == 200
    assert "v0.1.0" in created_tag.json()
    stash = client.get(f"/api/projects/{project_id}/git/stash")
    assert stash.status_code == 200


def test_sql_generation_refuses_to_overwrite_external_changes(tmp_path: Path):
    store = DataStore(tmp_path)
    project = store.create_project("sql-drift")
    source = Node(type="source.table", config={"table": "raw.orders"})
    output = Node(type="dataset.materialized_view", config={"name": "orders"})
    document = PipelineDocument(
        name="orders",
        nodes=[source, output],
        edges=[Edge(**{"from": PortRef(node=source.id), "to": PortRef(node=output.id, port="in")})],
    )
    store.save_pipeline(project["id"], document)
    first = store.generate_sql(project["id"])
    assert first.files
    generated = store.project_path(project["id"]) / "transformations" / "generated.sql"
    generated.write_text(
        generated.read_text(encoding="utf-8") + "-- external edit\n", encoding="utf-8"
    )

    refused = store.generate_sql(project["id"])
    assert refused.files == []
    assert any(problem.code == "SDPS-CODEGEN-DRIFT" for problem in refused.problems)
    assert "-- external edit" in generated.read_text(encoding="utf-8")


def test_canonical_pipeline_collection_and_resource_routes(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "pipeline-resource"}).json()
    document = {"name": "pipeline-resource", "nodes": [], "edges": []}
    created = client.post(f"/api/projects/{project['id']}/pipelines", json=document)
    assert created.status_code == 200
    assert created.json()["id"] == project["id"]
    listed = client.get(f"/api/projects/{project['id']}/pipelines")
    assert listed.status_code == 200
    assert listed.json()[0]["project_id"] == project["id"]
    detail = client.get(f"/api/pipelines/{project['id']}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "pipeline-resource"
    compatibility = client.get(f"/api/pipelines/{project['id']}/compatibility")
    assert compatibility.status_code == 200
    assert "compatible" in compatibility.json()
    preview = client.post(
        f"/api/pipelines/{project['id']}/preview", json={"node_id": "missing", "limit": 5}
    )
    assert preview.status_code == 200
    assert "ok" in preview.json()
    run = client.post(f"/api/pipelines/{project['id']}/runs", json={})
    assert run.status_code == 200
    assert run.json()["project_id"] == project["id"]


def test_history_checkpoint_and_retention_policy(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_HISTORY_MAX_COUNT", "2")
    store = DataStore(tmp_path)
    project = store.create_project("history-retention")
    checkpoint = store.create_history_checkpoint(project["id"], "before-release")
    assert checkpoint["reason"] == "checkpoint: before-release"
    document = store.load_pipeline(project["id"])
    for _ in range(4):
        document.revision = store.load_pipeline(project["id"]).revision
        store.save_pipeline(project["id"], document)
    assert len(store.list_history(project["id"])) <= 2


def test_rapid_pipeline_saves_coalesce_history_snapshots(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_HISTORY_DEBOUNCE_SECONDS", "60")
    store = DataStore(tmp_path)
    project = store.create_project("history-debounce")
    document = store.load_pipeline(project["id"])
    store.save_pipeline(project["id"], document.model_copy(deep=True))
    current = store.load_pipeline(project["id"])
    store.save_pipeline(project["id"], current.model_copy(deep=True))
    automatic = [
        item for item in store.list_history(project["id"]) if item["reason"] == "before visual edit"
    ]
    assert len(automatic) == 1


def test_history_retention_removes_snapshots_past_age_limit(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_HISTORY_MAX_COUNT", "20")
    monkeypatch.setenv("SDPSTUDIO_HISTORY_MAX_AGE_DAYS", "1")
    store = DataStore(tmp_path)
    project = store.create_project("history-age-retention")
    first = store.create_history_checkpoint(project["id"], "old")
    history_dir = store.project_path(project["id"]) / ".sdpstudio" / "history"
    first_path = next(history_dir.glob(f"*_{first['id']}.json"))
    import os
    import time

    old = time.time() - 86400
    os.utime(first_path, (old, old))
    monkeypatch.setenv("SDPSTUDIO_HISTORY_MAX_AGE_DAYS", "0")
    store.create_history_checkpoint(project["id"], "new")
    assert all(item["id"] != first["id"] for item in store.list_history(project["id"]))


def test_generation_refuses_to_overwrite_code_with_changed_ownership_hash(tmp_path: Path):
    app = create_app(tmp_path)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "drift"}).json()
    project_path = app.state.store.project_path(project["id"])
    generated = project_path / "transformations" / "generated.py"
    original = generated.read_text(encoding="utf-8")
    generated.write_text(original + "\n# external edit\n", encoding="utf-8")
    result = client.post(f"/api/projects/{project['id']}/generate").json()
    assert any(problem["code"] == "SDPS-CODEGEN-DRIFT" for problem in result["problems"])
    assert generated.read_text(encoding="utf-8") == original + "\n# external edit\n"


def test_project_file_api_supports_etags_and_blocks_traversal(tmp_path: Path):
    app = create_app(tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "files"}).json()["id"]

    written = client.put(
        f"/api/projects/{project_id}/files/transformations/custom.py",
        json={"content": "print('custom')\n"},
    )
    assert written.status_code == 200
    etag = written.json()["etag"]
    loaded = client.get(f"/api/projects/{project_id}/files/transformations/custom.py")
    assert loaded.status_code == 200
    assert loaded.json()["etag"] == etag
    conflict = client.put(
        f"/api/projects/{project_id}/files/transformations/custom.py",
        json={"content": "stale", "etag": "bad"},
    )
    assert conflict.status_code == 409
    traversal = client.get(f"/api/projects/{project_id}/files/../project.yaml")
    assert traversal.status_code in {400, 404}


def test_pipeline_schema_endpoint_is_machine_readable(tmp_path: Path):
    response = TestClient(create_app(tmp_path)).get("/api/schema/pipeline")
    assert response.status_code == 200
    assert response.json()["title"] == "PipelineDocument"
    assert "nodes" in response.json()["properties"]


def test_health_readiness_and_request_id_contract(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    health = client.get("/health")
    assert health.status_code == 200
    assert health.headers["x-request-id"]
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ok",
        "checks": {"database": "ok", "storage": "ok"},
    }


def test_plan_parse_api_is_fail_soft(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/debug/plan/parse",
        json={"explain": "== Physical Plan ==\n*(1) Filter\nunknown"},
    )
    assert response.status_code == 200
    assert response.json()["nodes"][0]["operator"] == "Filter"
    assert response.json()["raw_lines"] == ["unknown"]


def test_debug_plan_prefers_latest_captured_run_artifact(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "captured-plan"}).json()
    store = DataStore(tmp_path)
    run = RunRecord(project_id=project["id"], status="succeeded")
    store.create_run(run)
    artifact_dir = Path(project["path"]) / ".sdpstudio" / "runtime" / "run-artifacts" / run.id
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "plan.json").write_text(
        json.dumps({"plans": [{"node_id": "filter", "plan": "Filter"}]}),
        encoding="utf-8",
    )

    response = client.get(f"/api/projects/{project['id']}/debug/plan")

    assert response.status_code == 200
    assert response.json()["source"] == "captured_run_artifact"
    assert response.json()["run_id"] == run.id


def test_diagnostics_api_returns_rule_findings(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/debug/diagnostics",
        json={"error_class": "UNRESOLVED_COLUMN.WITH_SUGGESTION", "message": "missing"},
    )
    assert response.status_code == 200
    assert response.json()["findings"][0]["id"] == "spark.analysis.unresolved-column"


def test_schedule_api_persists_and_toggles_local_schedule(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project_id = client.post("/api/projects", json={"name": "scheduled"}).json()["id"]
    created = client.post(
        f"/api/projects/{project_id}/schedules",
        json={"name": "nightly", "cron": "0 0 * * *", "mode": "incremental"},
    )
    assert created.status_code == 200
    schedule_id = created.json()["id"]
    assert client.get(f"/api/projects/{project_id}/schedules").json()[0]["enabled"] is True
    assert client.get(f"/api/projects/{project_id}/schedules").json()[0]["next_fire"]
    assert client.app.state.store.claim_schedule(schedule_id, "2026-08-24T00:00") is True
    assert client.app.state.store.claim_schedule(schedule_id, "2026-08-24T00:00") is False
    disabled = client.patch(f"/api/schedules/{schedule_id}", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    updated = client.patch(
        f"/api/schedules/{schedule_id}",
        json={
            "name": "hourly-refresh",
            "cron": "0 * * * *",
            "mode": "refresh",
            "concurrency_policy": "replace",
            "missed_run_policy": "run_once",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "hourly-refresh"
    assert updated.json()["concurrency_policy"] == "replace"
    assert updated.json()["missed_run_policy"] == "run_once"
    bad = client.post(
        f"/api/projects/{project_id}/schedules",
        json={"name": "bad", "cron": "hourly bad"},
    )
    assert bad.status_code == 400


def test_schedule_api_supports_run_now_and_checks_project_ownership(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    first = client.post("/api/projects", json={"name": "scheduled-now"}).json()
    second = client.post("/api/projects", json={"name": "other-project"}).json()
    schedule = client.post(
        f"/api/projects/{first['id']}/schedules",
        json={"name": "manual", "cron": "0 0 * * *", "mode": "incremental"},
    ).json()
    submitted = client.post(f"/api/projects/{first['id']}/schedules/{schedule['id']}/run-now")
    assert submitted.status_code == 200
    assert submitted.json()["id"]
    wrong_project = client.post(f"/api/projects/{second['id']}/schedules/{schedule['id']}/run-now")
    assert wrong_project.status_code == 400


def test_secret_api_persists_metadata_without_plaintext(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_SECRET_KEY", "test-server-key-for-secrets")
    client = TestClient(create_app(tmp_path))
    response = client.put(
        "/api/secrets/spark-token",
        json={"name": "spark-token", "value": "very-private-value"},
    )
    assert response.status_code == 200
    assert "value" not in response.json()
    listed = client.get("/api/secrets")
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "spark-token"
    assert "very-private-value" not in listed.text


def test_local_auth_login_and_me(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "test-auth-signing-key")
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "administrator-password")
    client = TestClient(create_app(tmp_path))
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "administrator-password"},
    )
    assert login.status_code == 200
    assert "access_token" not in login.json()
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {"username": "admin", "role": "admin"}
    created = client.post(
        "/api/auth/users",
        headers={"X-CSRF-Token": client.cookies.get("sdpstudio_csrf")},
        json={"username": "editor", "password": "editor-password-123", "role": "editor"},
    )
    assert created.status_code == 200
    restarted = TestClient(create_app(tmp_path))
    editor_login = restarted.post(
        "/api/auth/login",
        json={"username": "editor", "password": "editor-password-123"},
    )
    assert editor_login.status_code == 200


def test_admin_can_update_user_role_and_audit_event_is_persisted(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "role-update-signing-key")
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "administrator-password")
    client = TestClient(create_app(tmp_path))
    admin_token = (
        client.post(
            "/api/auth/login", json={"username": "admin", "password": "administrator-password"}
        )
        .cookies.get("sdpstudio_session")
        .strip('"')
    )
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    assert (
        client.post(
            "/api/auth/users",
            headers=admin_headers,
            json={"username": "analyst", "password": "analyst-password-123", "role": "viewer"},
        ).status_code
        == 200
    )
    updated = client.patch(
        "/api/auth/users/analyst", headers=admin_headers, json={"role": "editor"}
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "editor"
    audit = client.get("/api/auth/audit", headers=admin_headers).json()
    assert any(item["action"] == "user.role_changed" for item in audit)

    restarted = TestClient(create_app(tmp_path))
    login = restarted.post(
        "/api/auth/login", json={"username": "analyst", "password": "analyst-password-123"}
    )
    assert login.status_code == 200
    assert "access_token" not in login.json()


def test_non_admin_cannot_update_user_role(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "role-rbac-signing-key")
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "administrator-password")
    client = TestClient(create_app(tmp_path))
    admin_token = (
        client.post(
            "/api/auth/login", json={"username": "admin", "password": "administrator-password"}
        )
        .cookies.get("sdpstudio_session")
        .strip('"')
    )
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": "viewer", "password": "viewer-password-123", "role": "viewer"},
    )
    viewer_token = (
        client.post(
            "/api/auth/login", json={"username": "viewer", "password": "viewer-password-123"}
        )
        .cookies.get("sdpstudio_session")
        .strip('"')
    )
    response = client.patch(
        "/api/auth/users/admin",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"role": "viewer"},
    )
    assert response.status_code == 403


def test_local_auth_session_authorizes_websocket(tmp_path: Path, monkeypatch):
    import base64

    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "test-auth-signing-key")
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "administrator-password")
    client = TestClient(create_app(tmp_path))
    token = (
        client.post(
            "/api/auth/login", json={"username": "admin", "password": "administrator-password"}
        )
        .cookies.get("sdpstudio_session")
        .strip('"')
    )
    project_id = client.post(
        "/api/projects", headers={"Authorization": f"Bearer {token}"}, json={"name": "ws-auth"}
    ).json()["id"]
    encoded = base64.urlsafe_b64encode(token.encode()).decode().rstrip("=")
    with client.websocket_connect(
        f"/ws/projects/{project_id}",
        subprotocols=["sdpstudio.v1", f"sdpstudio.auth.{encoded}"],
    ) as ws:
        assert ws.receive_json()["type"] == "presence"


def test_rbac_mutation_matrix_blocks_viewer_and_allows_editor_boundary(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "rbac-signing-key-123456")
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "admin-development-password")
    client = TestClient(create_app(tmp_path))
    admin_token = (
        client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin-development-password"}
        )
        .cookies.get("sdpstudio_session")
        .strip('"')
    )
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    for username, role in (("viewer", "viewer"), ("editor", "editor")):
        assert (
            client.post(
                "/api/auth/users",
                headers=admin_headers,
                json={
                    "username": username,
                    "password": f"{username}-development-password",
                    "role": role,
                },
            ).status_code
            == 200
        )
    project = client.post("/api/projects", headers=admin_headers, json={"name": "rbac"}).json()
    protected = client.post(
        "/api/runtime-profiles",
        headers=admin_headers,
        json={"name": "production", "adapter": "local", "is_protected": True},
    ).json()
    viewer = (
        client.post(
            "/api/auth/login",
            json={"username": "viewer", "password": "viewer-development-password"},
        )
        .cookies.get("sdpstudio_session")
        .strip('"')
    )
    viewer_headers = {"Authorization": f"Bearer {viewer}"}
    assert (
        client.post(f"/api/projects/{project['id']}/generate", headers=viewer_headers).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/projects/{project['id']}/runs", headers=viewer_headers, json={}
        ).status_code
        == 403
    )
    assert client.get("/api/secrets", headers=viewer_headers).status_code == 403

    schedule = client.post(
        f"/api/projects/{project['id']}/schedules",
        headers=admin_headers,
        json={"name": "nightly", "cron": "0 0 * * *"},
    ).json()
    assert (
        client.delete(f"/api/schedules/{schedule['id']}", headers=viewer_headers).status_code == 403
    )
    editor = (
        client.post(
            "/api/auth/login",
            json={"username": "editor", "password": "editor-development-password"},
        )
        .cookies.get("sdpstudio_session")
        .strip('"')
    )
    protected_run = client.post(
        f"/api/projects/{project['id']}/runs",
        headers={"Authorization": f"Bearer {editor}"},
        json={"runtime_profile_id": protected["id"]},
    )
    assert protected_run.status_code == 403
    assert protected_run.json()["detail"]["code"] == "SDPS-AUTH-ROLE_REQUIRED"
    assert protected_run.json()["detail"]["required_role"] == "admin"
    assert (
        client.delete(
            f"/api/schedules/{schedule['id']}", headers={"Authorization": f"Bearer {editor}"}
        ).status_code
        == 204
    )


def test_viewer_websocket_is_read_only_for_collaboration_updates(tmp_path: Path, monkeypatch):
    import base64

    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "rbac-ws-signing-key-123")
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "admin-development-password")
    client = TestClient(create_app(tmp_path))
    admin = (
        client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin-development-password"}
        )
        .cookies.get("sdpstudio_session")
        .strip('"')
    )
    headers = {"Authorization": f"Bearer {admin}"}
    client.post(
        "/api/auth/users",
        headers=headers,
        json={"username": "viewer", "password": "viewer-development-password", "role": "viewer"},
    )
    viewer = (
        client.post(
            "/api/auth/login",
            json={"username": "viewer", "password": "viewer-development-password"},
        )
        .cookies.get("sdpstudio_session")
        .strip('"')
    )
    project = client.post("/api/projects", headers=headers, json={"name": "viewer-ws"}).json()
    encoded = base64.urlsafe_b64encode(viewer.encode()).decode().rstrip("=")
    with client.websocket_connect(
        f"/ws/projects/{project['id']}", subprotocols=["sdpstudio.v1", f"sdpstudio.auth.{encoded}"]
    ) as ws:
        assert ws.receive_json()["type"] == "presence"
        ws.send_json({"type": "y_update", "update": "AQID"})
        assert ws.receive_json() == {"type": "error", "code": "COLLAB_READ_ONLY"}


def test_oidc_public_config_and_start(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "test-auth-signing-key")
    monkeypatch.setenv("SDPSTUDIO_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("SDPSTUDIO_OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("SDPSTUDIO_OIDC_REDIRECT_URI", "http://localhost/callback")
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/auth/oidc/config").json()["enabled"] is True
    started = client.get("/api/auth/oidc/start").json()
    assert "issuer.example/authorize" in started["authorization_url"]


def test_python_import_api_does_not_execute_source(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/import/python",
        json={
            "path": "pipeline.py",
            "source": "raise RuntimeError('no execute')\nfrom pyspark import pipelines as dp\n@dp.table()\ndef events():\n    return spark.readStream.table('raw.events')",
        },
    )
    assert response.status_code == 200
    assert response.json()["declarations"][0]["name"] == "events"
    assert response.json()["declarations"][0]["dependencies"] == ["raw.events"]


def test_sql_import_api_is_non_executing(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/import/sql", json={"source": "CREATE TEMP VIEW orders AS SELECT * FROM raw.orders"}
    )
    assert response.status_code == 200
    assert response.json()["declarations"][0]["kind"] == "dataset.temporary_view"


def test_schema_diff_api_returns_fingerprints_and_compatibility(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/debug/schema-diff",
        json={
            "before": [{"name": "id", "type": "integer"}],
            "after": [{"name": "id", "type": "long"}],
        },
    )
    assert response.status_code == 200
    assert len(response.json()["before_fingerprint"]) == 64
    assert response.json()["diff"]["compatible"] is False


def test_capability_validation_api_fails_closed(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project_id = client.post("/api/projects", json={"name": "capabilities"}).json()["id"]
    source = Node(
        type="source.kafka", config={"bootstrapServers": "kafka:9092", "subscribe": "events"}
    )
    output = Node(type="dataset.streaming_table", config={"name": "events"})
    doc = PipelineDocument(
        nodes=[source, output],
        edges=[Edge(**{"from": PortRef(node=source.id), "to": PortRef(node=output.id, port="in")})],
    )
    assert (
        client.put(
            f"/api/projects/{project_id}/pipeline", json=doc.model_dump(by_alias=True)
        ).status_code
        == 200
    )
    response = client.post(
        f"/api/projects/{project_id}/validate-capabilities",
        json={"available": True, "streaming_table": False},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["problems"][0]["code"] == "SDPS-CAP-001"


def test_bounded_profile_api(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/debug/profile", json={"rows": [{"id": 1}, {"id": None}]})
    assert response.status_code == 200
    assert response.json()["row_count"] == 2
    assert response.json()["columns"]["id"]["null_count"] == 1

    private = client.post(
        "/api/debug/profile",
        json={
            "rows": [{"amount": 2.0, "status": "private"}],
            "include_sensitive_metrics": False,
        },
    )
    assert private.status_code == 200
    assert "mean" not in private.json()["columns"]["amount"]
    assert "top_values" not in private.json()["columns"]["status"]


def test_row_trace_execution_api_is_bounded_and_side_effect_free(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project_id = client.post("/api/projects", json={"name": "trace-api"}).json()["id"]
    source = Node(id="source", type="source.table", config={"table": "orders"})
    filt = Node(id="filter", type="transform.filter", config={"expression": "amount > 10"})
    document = PipelineDocument(
        nodes=[source, filt],
        edges=[Edge.model_validate({"from": {"node": "source"}, "to": {"node": "filter"}})],
    )
    assert (
        client.put(
            f"/api/projects/{project_id}/pipeline", json=document.model_dump(by_alias=True)
        ).status_code
        == 200
    )
    response = client.post(
        f"/api/projects/{project_id}/debug/row-trace/execute",
        json={"node_id": "filter", "rows": [{"id": 1, "amount": 12}, {"id": 2, "amount": 3}]},
    )
    assert response.status_code == 200
    assert response.json()["rows"] == [{"id": 1, "amount": 12}]


def test_row_trace_without_rows_uses_runtime_preview_provenance(tmp_path: Path, monkeypatch):
    app = create_app(tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "trace-runtime"}).json()["id"]
    document = PipelineDocument(
        nodes=[Node(id="source", type="source.table", config={"table": "orders"})], edges=[]
    )
    client.put(f"/api/projects/{project_id}/pipeline", json=document.model_dump(by_alias=True))

    async def preview(_project_id, node_id, limit, **_options):
        return {
            "ok": True,
            "node_id": node_id,
            "limit": limit,
            "trace_rows": [{"id": 1, "__sdpstudio_trace_id": 101}],
        }

    monkeypatch.setattr(app.state.runtime, "preview", preview)
    response = client.post(
        f"/api/projects/{project_id}/debug/row-trace/execute", json={"node_id": "source"}
    )
    assert response.status_code == 200
    assert response.json()["execution_backed"] is True
    assert response.json()["runtime_trace_ids"] == [101]
    assert response.json()["provenance"] == "runtime_preview_rows"


def test_run_plan_artifact_is_served_from_run_scope(tmp_path: Path):
    app = create_app(tmp_path)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "plan-artifact"}).json()
    run = client.post(f"/api/projects/{project['id']}/runs", json={}).json()
    artifact = (
        Path(project["path"]) / ".sdpstudio" / "runtime" / "run-artifacts" / run["id"] / "plan.json"
    )
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"source":"spark_dataframe_explain","plans":[]}', encoding="utf-8")
    response = client.get(f"/api/runs/{run['id']}/plan")
    assert response.status_code == 200
    assert response.json()["source"] == "spark_dataframe_explain"


def test_run_detail_exposes_provider_identity_for_remote_runtime_profiles(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "provider-run"}).json()
    profile = client.post(
        "/api/runtime-profiles",
        json={
            "name": "managed-databricks",
            "adapter": "databricks-connect",
            "config": {"workspace_url": "https://workspace.example"},
        },
    ).json()
    run = client.post(
        f"/api/projects/{project['id']}/runs",
        json={"runtime_profile_id": profile["id"]},
    ).json()
    detail = client.get(f"/api/runs/{run['id']}")
    assert detail.status_code == 200
    assert detail.json()["provider"]["adapter"] == "databricks-connect"
    assert detail.json()["provider"]["workspace_url"] == "https://workspace.example"


def test_quality_evaluation_api_executes_bounded_operator_semantics(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project_id = client.post("/api/projects", json={"name": "quality-api"}).json()["id"]
    document = PipelineDocument(
        nodes=[
            Node(
                id="quality", type="quality.null_rate", config={"column": "value", "maxRate": 0.25}
            )
        ],
        edges=[],
    )
    client.put(f"/api/projects/{project_id}/pipeline", json=document.model_dump(by_alias=True))
    response = client.post(
        f"/api/projects/{project_id}/quality/evaluate",
        json={"node_id": "quality", "rows": [{"value": None}, {"value": 1}, {"value": 2}]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["failures"][0]["rule"] == "null_rate"


def test_quality_suite_api_loads_project_suite_and_evaluates_bounded_snapshots(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "quality-suite-api"}).json()
    suite = Path(project["path"]) / ".sdpstudio" / "tests" / "quality.yaml"
    suite.parent.mkdir(parents=True, exist_ok=True)
    suite.write_text(
        "checks:\n"
        "  - id: unique-orders\n"
        "    type: quality.uniqueness\n"
        "    mode: post-run\n"
        "    config:\n"
        "      columns: [id]\n",
        encoding="utf-8",
    )
    response = client.post(
        f"/api/projects/{project['id']}/quality/suite/evaluate",
        json={"rows_by_check": {"unique-orders": [{"id": 1}, {"id": 1}]}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["checks"][0]["id"] == "unique-orders"


def test_quality_suite_api_can_resolve_rows_from_preview(tmp_path: Path, monkeypatch):
    app = create_app(tmp_path)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "quality-auto"}).json()
    suite = Path(project["path"]) / ".sdpstudio" / "tests" / "quality.yaml"
    suite.parent.mkdir(parents=True, exist_ok=True)
    suite.write_text(
        "checks:\n"
        "  - id: unique-orders\n"
        "    type: quality.uniqueness\n"
        "    mode: post-run\n"
        "    config:\n"
        "      columns: [id]\n"
        "      nodeId: orders\n",
        encoding="utf-8",
    )

    async def preview(*args, **kwargs):
        return {"rows": [{"id": 1}, {"id": 1}]}

    monkeypatch.setattr(app.state.runtime_dispatch, "preview", preview)
    response = client.post(
        f"/api/projects/{project['id']}/quality/suite/evaluate",
        json={"automatic": True, "mode": "post-run"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"


def test_doctor_and_failed_run_are_actionable(tmp_path: Path):
    app = create_app(tmp_path)
    client = TestClient(app)
    p = client.post("/api/projects", json={"name": "empty"}).json()
    doctor = client.get("/api/doctor")
    assert doctor.status_code == 200
    assert "available" in doctor.json()

    # Empty project cannot generate an output and warns, but run creation is still blocked only by errors.
    run = client.post(f"/api/projects/{p['id']}/runs", json={"mode": "incremental", "selected": []})
    assert run.status_code == 200
    assert run.json()["status"] in {"queued", "failed"}


def test_revision_conflict_and_collaboration_notification(tmp_path: Path):
    app = create_app(tmp_path)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "collab"}).json()
    project_id = project["id"]
    initial = client.get(f"/api/projects/{project_id}/pipeline").json()

    with client.websocket_connect(f"/ws/projects/{project_id}") as ws:
        presence = ws.receive_json()
        assert presence["type"] == "presence"
        first = client.put(
            f"/api/projects/{project_id}/pipeline",
            json=initial,
            headers={"X-SDPStudio-Client-ID": "editor-a"},
        )
        assert first.status_code == 200
        event = ws.receive_json()
        while event.get("type") == "presence":
            event = ws.receive_json()
        assert event["type"] == "pipeline_saved"
        assert event["client_id"] == "editor-a"
        assert event["revision"] == 1

    with client.websocket_connect(f"/ws/projects/{project_id}") as replay_ws:
        assert replay_ws.receive_json()["type"] == "presence"
        replay = replay_ws.receive_json()
        assert replay["type"] == "snapshot"
        assert replay["snapshot"]["document"]["revision"] == 1

    stale = client.put(f"/api/projects/{project_id}/pipeline", json=initial)
    assert stale.status_code == 409
    assert stale.json()["detail"]["current_revision"] == 1


def test_bearer_auth_protects_api_but_not_shell(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_AUTH_TOKEN", "test-access-token-123")
    client = TestClient(create_app(tmp_path))
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/projects", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert (
        client.get(
            "/api/projects", headers={"Authorization": "Bearer test-access-token-123"}
        ).status_code
        == 200
    )


def test_clone_existing_svp_repository(tmp_path: Path, monkeypatch):
    from sdpstudio_server import git_service

    def fake_clone(remote_url: str, target: Path, branch: str | None = None):
        assert remote_url == "https://github.com/acme/pipelines.git"
        target.mkdir(parents=True)
        (target / ".git" / "info").mkdir(parents=True)
        (target / ".git" / "info" / "exclude").write_text("# local excludes\n", encoding="utf-8")
        (target / ".sdpstudio" / "pipelines").mkdir(parents=True)
        (target / ".sdpstudio" / "project.yaml").write_text("name: imported\n", encoding="utf-8")
        doc = PipelineDocument(name="imported")
        import yaml

        (target / ".sdpstudio" / "pipelines" / "main.sdpstudio.yaml").write_text(
            yaml.safe_dump(doc.model_dump(by_alias=True), sort_keys=False), encoding="utf-8"
        )
        return {"initialized": True}

    monkeypatch.setattr(git_service, "clone", fake_clone)
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/projects/clone",
        json={"name": "imported", "remote_url": "https://github.com/acme/pipelines.git"},
    )
    assert response.status_code == 200
    project = response.json()
    loaded = client.get(f"/api/projects/{project['id']}/pipeline")
    assert loaded.status_code == 200
    exclude = Path(project["path"]) / ".git" / "info" / "exclude"
    text = exclude.read_text(encoding="utf-8")
    assert ".sdpstudio/runtime/" in text
    assert ".sdpstudio/history/" in text


def test_websocket_auth_uses_subprotocol_not_query_string(tmp_path: Path, monkeypatch):
    import base64

    token = "team-secret-token"
    monkeypatch.setenv("SDPSTUDIO_AUTH_TOKEN", token)
    client = TestClient(create_app(tmp_path))
    headers = {"Authorization": f"Bearer {token}"}
    project = client.post("/api/projects", json={"name": "secure-collab"}, headers=headers).json()
    encoded = base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii").rstrip("=")
    with client.websocket_connect(
        f"/ws/projects/{project['id']}",
        subprotocols=["sdpstudio.v1", f"sdpstudio.auth.{encoded}"],
    ) as ws:
        presence = ws.receive_json()
        assert presence["type"] == "presence"
        assert ws.accepted_subprotocol == "sdpstudio.v1"


def test_audit_log_is_durable_and_admin_only(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "audit-signing-key-123456")
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "admin-development-password")
    monkeypatch.setenv("SDPSTUDIO_SECRET_KEY", "test-server-key-for-secrets")
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/auth/audit").status_code == 401
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin-development-password"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.cookies.get('sdpstudio_session').strip(chr(34))}"}
    secret = client.put(
        "/api/secrets/warehouse",
        json={"name": "warehouse", "value": "not-recorded"},
        headers=headers,
    )
    assert secret.status_code == 200
    project = client.post("/api/projects", json={"name": "audited"}, headers=headers)
    assert project.status_code == 200
    events = client.get("/api/auth/audit", headers=headers)
    assert events.status_code == 200
    actions = {event["action"] for event in events.json()}
    assert {"auth.login", "secret.changed", "project.created"} <= actions
    assert any(event["action"] == "project.created" for event in events.json())
    assert all("not-recorded" not in str(event) for event in events.json())


def test_redaction_preview_scans_registered_secrets_without_returning_values(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "redaction-signing-key-123456")
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "admin-development-password")
    monkeypatch.setenv("SDPSTUDIO_SECRET_KEY", "test-server-key-for-secrets")
    client = TestClient(create_app(tmp_path))
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin-development-password"},
    )
    headers = {"Authorization": f"Bearer {login.cookies.get('sdpstudio_session').strip(chr(34))}"}
    assert (
        client.put(
            "/api/secrets/warehouse",
            json={"name": "warehouse", "value": "registered-secret-value"},
            headers=headers,
        ).status_code
        == 200
    )
    response = client.post(
        "/api/debug/redaction-preview",
        json={"payload": {"command": "--password=registered-secret-value"}},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["matched_secret_names"] == ["warehouse"]
    assert "registered-secret-value" not in str(body)
    assert body["payload"]["command"] == "--password=***REDACTED***"


def test_cookie_session_requires_csrf_and_logout_revokes_session(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SDPSTUDIO_AUTH_SIGNING_KEY", "cookie-signing-key-123456")
    monkeypatch.setenv("SDPSTUDIO_ADMIN_PASSWORD", "admin-development-password")
    client = TestClient(create_app(tmp_path))
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin-development-password"},
    )
    assert login.status_code == 200
    assert "sdpstudio_session" in client.cookies and "sdpstudio_csrf" in client.cookies
    assert client.post("/api/projects", json={"name": "blocked"}).status_code == 403
    csrf = client.cookies.get("sdpstudio_csrf")
    created = client.post(
        "/api/projects", json={"name": "csrf-protected"}, headers={"X-CSRF-Token": csrf}
    )
    assert created.status_code == 200
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/projects").status_code == 401


def test_debug_bundle_redacts_secrets_and_contains_hash_manifest(tmp_path: Path):
    app = create_app(tmp_path)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "bundle"}).json()
    run = client.post(
        f"/api/projects/{project['id']}/runs", json={"mode": "incremental", "selected": []}
    ).json()
    artifact_dir = Path(project["path"]) / ".sdpstudio" / "runtime" / "run-artifacts" / run["id"]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "event-summary.json").write_text(
        json.dumps({"authorization": "Bearer super-secret-token", "rows": 2}), encoding="utf-8"
    )
    response = client.get(f"/api/runs/{run['id']}/debug-bundle")
    assert response.status_code == 200
    bundle = artifact_dir / "debug-bundle.zip"
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert {item["path"] for item in manifest["files"]} >= {
            "run.json",
            "events.json",
            "event-summary.json",
        }
        content = b"".join(archive.read(name) for name in archive.namelist())
        assert b"super-secret-token" not in content
        for item in manifest["files"]:
            data = archive.read(item["path"])
            assert hashlib.sha256(data).hexdigest() == item["sha256"]


def test_run_artifacts_are_listed_downloadable_and_path_safe(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "artifacts"}).json()
    run = client.post(f"/api/projects/{project['id']}/runs", json={}).json()
    root = Path(project["path"]) / ".sdpstudio" / "runtime" / "run-artifacts" / run["id"]
    (root / "event-logs").mkdir(parents=True, exist_ok=True)
    (root / "event-logs" / "progress.json").write_text('{"batch": 1}', encoding="utf-8")
    (root / "process.json").write_text('{"pid": 1}', encoding="utf-8")

    listed = client.get(f"/api/runs/{run['id']}/artifacts")
    assert listed.status_code == 200
    assert "event-logs/progress.json" in [item["name"] for item in listed.json()]
    item = next(item for item in listed.json() if item["name"] == "event-logs/progress.json")
    downloaded = client.get(item["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.text == '{"batch": 1}'
    assert client.get(f"/api/runs/{run['id']}/artifacts/../run-snapshot.json").status_code in {
        400,
        404,
    }


def test_collaboration_websocket_persists_and_replays_yjs_updates(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "crdt"}).json()
    update = "AQID"
    with client.websocket_connect(f"/ws/projects/{project['id']}") as ws:
        assert ws.receive_json()["type"] == "presence"
        ws.send_json({"type": "y_update", "update": update, "client_id": "editor-a"})
        message = ws.receive_json()
        while message.get("type") == "presence":
            message = ws.receive_json()
        assert message["type"] == "y_update"
        assert message["event"]["update"] == update
    with client.websocket_connect(f"/ws/projects/{project['id']}") as ws:
        assert ws.receive_json()["type"] == "presence"
        replay = ws.receive_json()
        assert replay["type"] == "replay"
        assert replay["event"]["type"] == "y_update"


def test_collaboration_websocket_rejects_noncanonical_base64_updates(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "strict-crdt"}).json()
    with client.websocket_connect(f"/ws/projects/{project['id']}") as ws:
        assert ws.receive_json()["type"] == "presence"
        ws.send_json({"type": "y_update", "update": "AQID!"})
        assert ws.receive_json() == {"type": "error", "code": "COLLAB_INVALID_UPDATE"}


def test_collaboration_updates_compact_into_replayable_snapshot(tmp_path: Path):
    from sdpstudio_server.storage import DataStore

    store = DataStore(tmp_path)
    project = store.create_project("compact")
    for index in range(100):
        event = store.append_collaboration_event(
            project["id"], {"type": "y_update", "update": f"AQ{index:02d}"}
        )
        assert event["seq"] == index + 1

    snapshot = store.collaboration_snapshot(project["id"])
    assert snapshot is not None
    assert snapshot["seq"] == 100
    assert snapshot["document"]["format"] == "yjs-update-bundle"
    assert len(snapshot["document"]["updates"]) == 100
    assert store.collaboration_events(project["id"]) == []

    next_event = store.append_collaboration_event(
        project["id"], {"type": "y_update", "update": "AQnext"}
    )
    assert next_event["seq"] == 101
    assert store.collaboration_events(project["id"])[0]["seq"] == 101


def test_run_snapshot_captures_secret_safe_runtime_profile(tmp_path: Path):
    from sdpstudio_runners.local import _safe_runtime_profile

    app = create_app(tmp_path)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "provenance"}).json()
    profile = {
        "adapter": "spark-connect",
        "config": {"remote_env": "SPARK_REMOTE", "token": "do-not-persist-this-token"},
    }
    assert _safe_runtime_profile(profile)["config"]["token"] == "***REDACTED***"
    run = client.post(
        f"/api/projects/{project['id']}/runs",
        json={"mode": "incremental", "selected": [], "runtime_profile_id": None},
    ).json()
    # The default profile is still recorded even when the runtime probe fails locally.
    snapshot = (
        Path(project["path"])
        / ".sdpstudio"
        / "runtime"
        / "run-artifacts"
        / run["id"]
        / "run-snapshot.json"
    )
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    assert payload["runtime_profile"]["adapter"] == "local"


def test_kubernetes_run_observability_is_explicit_for_local_runs(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "local-only"}).json()
    run = client.post(f"/api/projects/{project['id']}/runs", json={}).json()
    status = client.get(f"/api/runs/{run['id']}/kubernetes/status")
    assert status.status_code == 200
    assert status.json() == {
        "ok": False,
        "supported": False,
        "message": "Run is not a Kubernetes submission",
    }
    logs = client.get(f"/api/runs/{run['id']}/kubernetes/logs?tail=0")
    assert logs.status_code == 400


def test_run_compare_returns_complete_comparison_contract(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "compare-contract"}).json()
    first = client.post(f"/api/projects/{project['id']}/runs", json={}).json()
    second = client.post(
        f"/api/projects/{project['id']}/runs", json={"mode": "full-refresh-all"}
    ).json()
    for run_id, shuffle in ((first["id"], 10), (second["id"], 25)):
        artifact = Path(project["path"]) / ".sdpstudio" / "runtime" / "run-artifacts" / run_id
        (artifact / "event-summary.json").write_text(
            json.dumps(
                {
                    "stages": [
                        {"stage_id": 1, "shuffle_read_bytes": shuffle, "shuffle_write_bytes": 2}
                    ]
                }
            ),
            encoding="utf-8",
        )
    for run_id, operator in ((first["id"], "Filter"), (second["id"], "Project")):
        artifact = Path(project["path"]) / ".sdpstudio" / "runtime" / "run-artifacts" / run_id
        (artifact / "plan.json").write_text(
            json.dumps(
                {"plans": [{"node_id": "orders", "parsed": {"nodes": [{"operator": operator}]}}]}
            ),
            encoding="utf-8",
        )
    for run_id, row_count in ((first["id"], 10), (second["id"], 14)):
        snapshot = client.post(
            f"/api/projects/{project['id']}/runs/{run_id}/node-snapshots",
            json={
                "node_id": "orders",
                "schema": [{"name": "id", "type": "long"}],
                "profile": {
                    "row_count": row_count,
                    "columns": {"id": {"null_count": 0, "distinct_count": row_count}},
                },
            },
        )
        assert snapshot.status_code == 200
    response = client.post(
        f"/api/projects/{project['id']}/debug/compare-runs",
        json={"left_run_id": first["id"], "right_run_id": second["id"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert {
        "source_diff",
        "runtime_diff",
        "node_metric_deltas",
        "schema_diffs",
        "problems_delta",
        "plan_diff_available",
    } <= payload.keys()
    assert {"left_code_hash", "right_code_hash", "unified_diff"} <= payload["source_diff"].keys()
    assert payload["node_metric_deltas"]["available"] is True
    assert payload["node_metric_deltas"]["stages"][0]["shuffle_read_bytes_delta"] == 15
    assert payload["quality_diffs"]["available"] is True
    assert payload["quality_diffs"]["nodes"]["orders"]["diff"]["status"] in {
        "changed",
        "insufficient_data",
    }
    assert payload["plan_diff"]["available"] is True
    assert payload["plan_diff"]["nodes"][0]["diff"]["operations"][0]["op"] == "replace"


def test_schema_timeline_endpoint_reads_persisted_run_snapshots(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "schema-timeline"}).json()
    first = client.post(f"/api/projects/{project['id']}/runs", json={}).json()
    second = client.post(f"/api/projects/{project['id']}/runs", json={}).json()
    for run_id, data_type in ((first["id"], "long"), (second["id"], "string")):
        response = client.post(
            f"/api/projects/{project['id']}/runs/{run_id}/node-snapshots",
            json={"node_id": "orders", "schema": [{"name": "id", "type": data_type}]},
        )
        assert response.status_code == 200
    response = client.get(f"/api/projects/{project['id']}/debug/schema-timeline")
    assert response.status_code == 200
    timeline = response.json()["timeline"]
    assert len(timeline) == 2
    assert timeline[1]["changed"] is True


def test_local_catalog_lists_project_data_without_executing_sources(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "orders.csv").write_text("id,status\n1,COMPLETE\n", encoding="utf-8")
    (tmp_path / "transformations.py").write_text(
        "raise RuntimeError('must not run')", encoding="utf-8"
    )

    result = local_catalog(tmp_path)

    assert result["catalog"] == "local"
    assert result["tables"] == [
        {
            "name": "orders",
            "path": "data/orders.csv",
            "format": "csv",
            "columns": ["id", "status"],
        }
    ]


def test_versioned_api_alias_supports_project_and_catalog_routes(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    created = client.post("/api/v1/projects", json={"name": "versioned"})
    assert created.status_code == 200
    project_id = created.json()["id"]

    catalog = client.get(f"/api/v1/projects/{project_id}/catalog")
    assert catalog.status_code == 200
    assert catalog.json()["catalog"] == "local"


def test_catalog_route_queries_runtime_profile_command(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "runtime-catalog"}).json()
    profile = client.post(
        "/api/runtime-profiles",
        json={
            "name": "catalog-runtime",
            "adapter": "local",
            "config": {
                "catalog_command": [
                    sys.executable,
                    "-c",
                    'print(\'{"catalog":"main","namespace":"sales","tables":[{"name":"orders"}]}\')',
                ]
            },
        },
    )
    assert profile.status_code == 200
    response = client.get(
        f"/api/projects/{project['id']}/catalog",
        params={"runtime_profile_id": profile.json()["id"]},
    )
    assert response.status_code == 200
    assert response.json()["source"] == "runtime-command"
    assert response.json()["tables"][0]["name"] == "orders"


def test_debug_bundle_preview_returns_redacted_manifest_before_export(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    project = client.post("/api/projects", json={"name": "bundle-preview"}).json()
    run = client.post(f"/api/projects/{project['id']}/runs", json={"mode": "incremental"}).json()
    response = client.get(f"/api/runs/{run['id']}/debug-bundle/preview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema"] == 1
    assert payload["redacted"] is True
    assert {item["path"] for item in payload["files"]} >= {"README.txt", "run.json"}
