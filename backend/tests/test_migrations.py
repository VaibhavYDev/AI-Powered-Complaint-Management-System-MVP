"""Migrations must build the schema from empty and must preserve rows that predate ownership."""

import os
import uuid

import pytest
import sqlalchemy as sa
from alembic import command

from app.migrate import _config

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")
requires_postgres = pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is not set")


def run(url: str, target: str = "head") -> None:
    from app import config

    original = config.settings.database_url
    config.settings.database_url = url
    try:
        command.upgrade(_config(), target)
    finally:
        config.settings.database_url = original


def test_upgrade_from_empty_creates_the_whole_schema(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    run(url)

    inspector = sa.inspect(sa.create_engine(url))
    assert {"complaints", "users"} <= set(inspector.get_table_names())
    assert "owner_id" in {c["name"] for c in inspector.get_columns("complaints")}
    assert "ix_complaints_owner" in {i["name"] for i in inspector.get_indexes("complaints")}


def test_existing_rows_survive_the_ownership_migration(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = sa.create_engine(url)

    run(url, "0001")  # schema as it was before ownership existed
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "insert into complaints (source, complainant, product, complaint, patient)"
                " values ('chat', '{}', '{\"batch_number\": \"PCM24031\"}', '{}', '{}')"
            )
        )

    run(url, "head")
    with engine.connect() as conn:
        rows = conn.execute(sa.text("select owner_id, product from complaints")).all()
    assert len(rows) == 1
    owner_id, product = rows[0]
    assert owner_id is None  # not handed to an arbitrary account
    assert "PCM24031" in product


def test_baseline_is_safe_on_a_database_that_already_has_the_table(tmp_path):
    url = f"sqlite:///{tmp_path / 'existing.db'}"
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("create table complaints (id integer primary key, source varchar(16))"))

    run(url)  # must not fail on the pre-existing table
    inspector = sa.inspect(engine)
    assert "owner_id" in {c["name"] for c in inspector.get_columns("complaints")}


# --- PostgreSQL ---------------------------------------------------------------------------------
# The deployment target is PostgreSQL, where 0002 also creates a foreign key that SQLite cannot
# express. These run when TEST_POSTGRES_URL points at a disposable database (CI provides one).

LEGACY_SCHEMA = """
create table complaints (
    id serial primary key,
    source varchar(16) not null,
    complainant jsonb not null,
    product jsonb not null,
    complaint jsonb not null,
    patient jsonb not null,
    risk_assessment jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
)
"""


@pytest.fixture
def postgres_schema():
    """An empty schema of its own, dropped afterwards, so tests cannot collide."""
    name = f"mig_{uuid.uuid4().hex[:10]}"
    admin = sa.create_engine(
        POSTGRES_URL, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 5}
    )
    with admin.connect() as conn:
        conn.execute(sa.text(f'create schema "{name}"'))
    url = f"{POSTGRES_URL}{'&' if '?' in POSTGRES_URL else '?'}options=-csearch_path%3D{name}"
    try:
        yield url, name, admin
    finally:
        with admin.connect() as conn:
            conn.execute(sa.text(f'drop schema "{name}" cascade'))
        admin.dispose()


@requires_postgres
def test_postgres_upgrade_from_empty(postgres_schema):
    url, name, admin = postgres_schema
    run(url)

    inspector = sa.inspect(sa.create_engine(url))
    assert {"complaints", "users"} <= set(inspector.get_table_names(schema=name))
    assert "owner_id" in {c["name"] for c in inspector.get_columns("complaints", schema=name)}
    keys = inspector.get_foreign_keys("complaints", schema=name)
    assert any(k["referred_table"] == "users" and k["constrained_columns"] == ["owner_id"] for k in keys)


@requires_postgres
def test_postgres_legacy_schema_with_records_is_migrated_in_place(postgres_schema):
    url, name, admin = postgres_schema
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text(LEGACY_SCHEMA))
        conn.execute(
            sa.text(
                "insert into complaints (source, complainant, product, complaint, patient, risk_assessment)"
                " values ('chat', '{\"name\": \"Rahul Sharma\"}', '{\"batch_number\": \"PCM24031\"}',"
                " '{\"defect_category\": \"physical_defect\"}', '{}', '{\"severity_class\": \"III\"}')"
            )
        )

    run(url)

    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "select owner_id, product->>'batch_number', complainant->>'name',"
                " risk_assessment->>'severity_class' from complaints"
            )
        ).all()
    assert row == [(None, "PCM24031", "Rahul Sharma", "III")]  # data intact, owned by nobody

    inspector = sa.inspect(engine)
    assert "ix_complaints_owner" in {i["name"] for i in inspector.get_indexes("complaints", schema=name)}
    engine.dispose()


@requires_postgres
def test_postgres_upgrade_is_repeatable(postgres_schema):
    url, _, _ = postgres_schema
    run(url)
    run(url)  # already at head: must be a no-op, not an error
