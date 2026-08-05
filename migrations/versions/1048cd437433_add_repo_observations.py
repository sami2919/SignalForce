"""add repo_observations

Revision ID: 1048cd437433
Revises: 10a15fbb92b1
Create Date: 2026-08-04 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1048cd437433"
down_revision: Union[str, Sequence[str], None] = "10a15fbb92b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "repo_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner_login", sa.String(length=255), nullable=False),
        sa.Column("html_url", sa.Text(), nullable=False),
        sa.Column("created_at_gh", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stars_at_first_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "full_name"),
    )
    op.create_index(
        "ix_repo_observations_first_seen",
        "repo_observations",
        ["tenant_id", "first_seen_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_repo_observations_first_seen", table_name="repo_observations")
    op.drop_table("repo_observations")
