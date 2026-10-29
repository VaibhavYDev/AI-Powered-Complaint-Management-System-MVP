from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401  (registers tables on Base)
from app.config import settings
from app.db import Base

target_metadata = Base.metadata


def run_migrations() -> None:
    if context.is_offline_mode():
        context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    # The URL is passed to the engine directly: a password containing '%' would otherwise be
    # mangled by alembic.ini interpolation.
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
