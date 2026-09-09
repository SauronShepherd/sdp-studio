"""Persist immutable external identity mappings and relink state."""

import sqlalchemy as sa
from alembic import op

revision = "0005_external_principals"
down_revision = "0004_project_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_principals",
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("email", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["username"], ["users.username"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("issuer", "subject"),
    )
    op.create_index(
        "ix_external_principals_username",
        "external_principals",
        ["username"],
        unique=False,
    )
    op.add_column(
        "users",
        sa.Column("external_identity_status", sa.String(length=32), nullable=False, server_default="local"),
    )
    # Legacy rows that carried an OIDC marker were created before issuer+subject
    # became authoritative. They cannot be safely rebound automatically.
    op.execute(
        "UPDATE users SET external_identity_status='pending_relink' "
        "WHERE oidc_subject IS NOT NULL AND TRIM(oidc_subject) <> ''"
    )


def downgrade() -> None:
    op.drop_column("users", "external_identity_status")
    op.drop_index("ix_external_principals_username", table_name="external_principals")
    op.drop_table("external_principals")
