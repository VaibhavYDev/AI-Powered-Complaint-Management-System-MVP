"""Baseline complaints table.

Written to be safe on a database that already holds this table from the pre-migration
create_all(): it only creates what is missing and never touches existing rows.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JsonColumn = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    if "complaints" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "complaints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("complainant", JsonColumn, nullable=False),
        sa.Column("product", JsonColumn, nullable=False),
        sa.Column("complaint", JsonColumn, nullable=False),
        sa.Column("patient", JsonColumn, nullable=False),
        sa.Column("risk_assessment", JsonColumn, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("complaints")
