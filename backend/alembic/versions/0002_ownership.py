"""Workspace owners.

Additive: `complaints.owner_id` is nullable, so rows written before ownership existed keep
their data and are simply owned by nobody. They are unreachable through the API, which is
the safe outcome - they are not handed to an arbitrary account.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "users" not in inspector.get_table_names():
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(320), nullable=True, unique=True),
            sa.Column("password_hash", sa.String(128), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    columns = {c["name"] for c in inspector.get_columns("complaints")}
    if "owner_id" not in columns:
        op.add_column("complaints", sa.Column("owner_id", sa.Integer(), nullable=True))
        op.create_index("ix_complaints_owner", "complaints", ["owner_id"])
        # SQLite (tests) cannot ALTER a constraint into an existing table; PostgreSQL, the
        # deployment target, gets the real foreign key.
        if op.get_bind().dialect.name != "sqlite":
            op.create_foreign_key("fk_complaints_owner", "complaints", "users", ["owner_id"], ["id"])


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_complaints_owner", "complaints", type_="foreignkey")
    op.drop_index("ix_complaints_owner", table_name="complaints")
    op.drop_column("complaints", "owner_id")
    op.drop_table("users")
