"""Bring the Alembic schema in line with the SDP Studio persistence model."""

import sqlalchemy as sa
from alembic import op

revision = "0002_spec_entities"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("username", sa.String(120), primary_key=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "secrets",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("key_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "schedules",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("project_id", sa.String(26), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("cron", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("runtime_profile_id", sa.String(26), nullable=True),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("last_claim_marker", sa.String(120), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "run_events",
        sa.Column("run_id", sa.String(26), sa.ForeignKey("runs.id"), primary_key=True),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(26), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "collaboration_events",
        sa.Column("project_id", sa.String(26), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("event_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "collaboration_snapshots",
        sa.Column("project_id", sa.String(26), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("document_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workspace_members",
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), primary_key=True),
        sa.Column("user_id", sa.String(26), nullable=False, primary_key=True),
        sa.Column("role", sa.String(32), nullable=False),
    )
    op.create_table(
        "repositories",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("project_id", sa.String(26), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("remote_url_redacted", sa.Text(), nullable=False),
        sa.Column("provider_type", sa.String(64), nullable=False),
        sa.Column("default_branch", sa.String(200), nullable=False),
        sa.Column("working_copy_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("project_id", sa.String(26), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "local_revisions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("project_id", sa.String(26), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("document_path", sa.Text(), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        # Runtime SQLite/PostgreSQL bootstrap stores revision content as text;
        # keep the migration type aligned for round-trip portability.
        sa.Column("content_blob", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(120), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("path_or_uri", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "node_snapshots",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("node_id", sa.String(26), nullable=False),
        sa.Column("schema_json", sa.Text(), nullable=True),
        sa.Column("profile_json", sa.Text(), nullable=True),
        sa.Column("metrics_json", sa.Text(), nullable=True),
        sa.Column("plan_artifact_id", sa.String(26), nullable=True),
    )
    for table, columns in {
        "projects": [
            sa.Column("workspace_id", sa.String(26), nullable=True),
            sa.Column("slug", sa.String(120), nullable=True),
            sa.Column("root_path", sa.Text(), nullable=True),
            sa.Column("repository_id", sa.String(26), nullable=True),
        ],
        "runtime_profiles": [
            sa.Column("workspace_id", sa.String(26), nullable=True),
            sa.Column("adapter_type", sa.String(64), nullable=True),
            sa.Column("is_protected", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        ],
        "runs": [
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("exit_code", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("pipeline_id", sa.String(26), nullable=True),
            sa.Column("runtime_profile_id", sa.String(26), nullable=True),
            sa.Column("run_type", sa.String(32), nullable=False, server_default="pipeline"),
            sa.Column("graph_revision_hash", sa.String(64), nullable=True),
            sa.Column("git_commit", sa.String(64), nullable=True),
            sa.Column("git_dirty", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("dirty_patch_hash", sa.String(64), nullable=True),
            sa.Column("source_hash", sa.String(64), nullable=True),
            sa.Column("external_run_id", sa.String(200), nullable=True),
            sa.Column("claim_token", sa.String(200), nullable=True),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        ],
        "secrets": [
            sa.Column("workspace_id", sa.String(26), nullable=True),
            sa.Column("encrypted_value", sa.Text(), nullable=True),
            sa.Column("key_version", sa.String(64), nullable=True),
        ],
        "schedules": [
            sa.Column("pipeline_id", sa.String(26), nullable=True),
            sa.Column("concurrency_policy", sa.String(32), nullable=True),
            sa.Column("missed_run_policy", sa.String(32), nullable=True),
            sa.Column("next_fire_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_fire_at", sa.DateTime(timezone=True), nullable=True),
        ],
    }.items():
        for column in columns:
            op.add_column(table, column)


def downgrade() -> None:
    # Reverse the upgrade in dependency order. Keeping this complete is
    # important for local rollback tests and for operators rehearsing upgrades.
    for table in (
        "node_snapshots",
        "artifacts",
        "local_revisions",
        "documents",
        "repositories",
        "workspace_members",
        "workspaces",
        "collaboration_snapshots",
        "collaboration_events",
        "audit_events",
        "run_events",
        "schedules",
        "secrets",
        "users",
    ):
        op.drop_table(table)
    for table, columns in {
        "runs": [
            "heartbeat_at",
            "claimed_at",
            "claim_token",
            "external_run_id",
            "source_hash",
            "dirty_patch_hash",
            "git_dirty",
            "git_commit",
            "graph_revision_hash",
            "run_type",
            "runtime_profile_id",
            "pipeline_id",
            "error",
            "exit_code",
            "finished_at",
            "started_at",
        ],
        "runtime_profiles": ["updated_at", "is_protected", "adapter_type", "workspace_id"],
        "projects": ["repository_id", "root_path", "slug", "workspace_id"],
    }.items():
        for column in columns:
            op.drop_column(table, column)
