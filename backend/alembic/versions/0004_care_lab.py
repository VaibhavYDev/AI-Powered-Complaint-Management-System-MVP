"""Care Documentation Reliability Lab tables.

Additive and independent of the complaint tables.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

JsonColumn = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "care_records" not in tables:
        op.create_table(
            "care_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="needs_review"),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("source_text", sa.Text(), nullable=True),
            sa.Column("care_plan", JsonColumn, nullable=True),
            sa.Column("note", JsonColumn, nullable=False),
            sa.Column("evidence", JsonColumn, nullable=True),
            sa.Column("alerts", JsonColumn, nullable=True),
            sa.Column("acknowledged", JsonColumn, nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_care_records_owner", "care_records", ["owner_id"])

    if "care_events" not in tables:
        op.create_table(
            "care_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("care_id", sa.Integer(), sa.ForeignKey("care_records.id"), nullable=False),
            sa.Column("actor_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(32), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_care_events_record", "care_events", ["care_id"])


def downgrade() -> None:
    op.drop_index("ix_care_events_record", table_name="care_events")
    op.drop_table("care_events")
    op.drop_index("ix_care_records_owner", table_name="care_records")
    op.drop_table("care_records")
