"""Schema upgrades. The application never creates tables implicitly; alembic owns the schema."""

from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[1]


def _config() -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return config


def upgrade_to_head() -> None:
    command.upgrade(_config(), "head")
