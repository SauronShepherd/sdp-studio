"""Add canonical identity and execution-event contract fields."""

import sqlalchemy as sa
from alembic import op

revision = "0003_contract_fields"
down_revision = "0002_spec_entities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable additions preserve existing local installations while allowing
    # new persistence paths to use the specification's stable identifiers.
    for _name, column in (
        ("id", sa.Column("id", sa.String(26), nullable=True)),
        ("email", sa.Column("email", sa.String(320), nullable=True)),
        ("display_name", sa.Column("display_name", sa.String(200), nullable=True)),
        ("oidc_subject", sa.Column("oidc_subject", sa.String(255), nullable=True)),
        ("is_active", sa.Column("is_active", sa.Boolean(), nullable=True)),
        ("last_login", sa.Column("last_login", sa.DateTime(timezone=True), nullable=True)),
    ):
        op.add_column("users", column)
    for table, columns in {
        "runs": [sa.Column("user_id", sa.String(26), nullable=True)],
        "run_events": [
            sa.Column("severity", sa.String(16), nullable=True),
            sa.Column("node_id", sa.String(26), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=True),
        ],
        "schedules": [sa.Column("parameters_json", sa.Text(), nullable=True)],
        "audit_events": [
            sa.Column("workspace_id", sa.String(26), nullable=True),
            sa.Column("actor_user_id", sa.String(26), nullable=True),
        ],
    }.items():
        for column in columns:
            op.add_column(table, column)


def downgrade() -> None:
    for table, columns in {
        "audit_events": ["actor_user_id", "workspace_id"],
        "schedules": ["parameters_json"],
        "run_events": ["payload_json", "node_id", "severity"],
        "runs": ["user_id"],
        "users": ["last_login", "is_active", "oidc_subject", "display_name", "email", "id"],
    }.items():
        for column in columns:
            op.drop_column(table, column)
