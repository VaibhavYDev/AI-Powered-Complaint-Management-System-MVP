"""Review state, evidence and audit trail.

Additive: existing complaints become `needs_review` at revision 1 with no evidence recorded,
which is the correct default for rows extracted before provenance was captured.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

JsonColumn = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("complaints")}

    for column in (
        sa.Column("status", sa.String(16), nullable=False, server_default="needs_review"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("evidence", JsonColumn, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
    ):
        if column.name not in columns:
            op.add_column("complaints", column)

    if "complaint_events" not in inspector.get_table_names():
        op.create_table(
            "complaint_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("complaint_id", sa.Integer(), sa.ForeignKey("complaints.id"), nullable=False),
            sa.Column("actor_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(32), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("changed_fields", JsonColumn, nullable=True),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_complaint_events_complaint", "complaint_events", ["complaint_id"])


def downgrade() -> None:
    op.drop_index("ix_complaint_events_complaint", table_name="complaint_events")
    op.drop_table("complaint_events")
    for name in ("reviewed_by", "reviewed_at", "evidence", "source_text", "revision", "status"):
        op.drop_column("complaints", name)
