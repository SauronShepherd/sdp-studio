"""Add a recoverable project deletion marker."""

import sqlalchemy as sa
from alembic import op

revision = "0004_project_soft_delete"
down_revision = "0003_contract_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "deleted_at")
