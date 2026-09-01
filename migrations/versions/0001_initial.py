"""Initial persistence tables."""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("path", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "runtime_profiles",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("adapter", sa.String(64), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("project_id", sa.String(26), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("selected_json", sa.Text(), nullable=False),
        sa.Column("command_json", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("runs")
    op.drop_table("runtime_profiles")
    op.drop_table("projects")
