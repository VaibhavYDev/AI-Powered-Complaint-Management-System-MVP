"""Migrations must build the schema from empty and must preserve rows that predate ownership."""

import sqlalchemy as sa
from alembic import command

from app.migrate import _config


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
