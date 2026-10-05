"""add source_health

Revision ID: a1c2e4f68b3d
Revises: e6a3e65f1070
Create Date: 2026-08-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1c2e4f68b3d"
down_revision: Union[str, Sequence[str], None] = "e6a3e65f1070"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "source_health",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("fetch_success_rate", sa.Float(), nullable=True),
        sa.Column("parse_success_rate", sa.Float(), nullable=True),
        sa.Column("zero_result_rate", sa.Float(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_type", "run_date", name="uq_source_health_tenant_source_date"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("source_health")
