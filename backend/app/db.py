from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


def connect_args(url: str) -> dict:
    # Without a bounded connect timeout an unreachable database blocks the process at startup,
    # the port is never bound, and the platform's router waits forever instead of showing an error.
    if url.startswith("postgres"):
        return {"connect_timeout": settings.db_connect_timeout}
    return {}


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,  # serverless Postgres drops idle connections
    connect_args=connect_args(settings.database_url),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
