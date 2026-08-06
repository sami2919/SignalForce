"""add fact_snapshots

Revision ID: f3b7c1a92e04
Revises: a1c2e4f68b3d
Create Date: 2026-08-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f3b7c1a92e04"
down_revision: Union[str, Sequence[str], None] = "a1c2e4f68b3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "fact_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_source_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default="{}",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["account_source_id"], ["account_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_source_id", name="uq_fact_snapshots_account_source_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("fact_snapshots")
