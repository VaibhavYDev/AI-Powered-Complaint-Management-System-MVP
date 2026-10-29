from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# JSONB on PostgreSQL; plain JSON elsewhere so the API tests can run on SQLite.
JsonColumn = JSON().with_variant(JSONB, "postgresql")


class User(Base):
    """A workspace owner. `email` is null for the anonymous sessions the public demo hands out."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComplaintRecord(Base):
    """One customer complaint. Each form section is stored as a JSON document that
    mirrors the canonical Pydantic schema, so the record round-trips without mapping code."""

    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable so the migration can add it without touching rows that predate ownership;
    # those rows belong to nobody and are therefore unreachable through the API.
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(16))  # "chat" | "document"
    complainant: Mapped[dict] = mapped_column(JsonColumn, default=dict)
    product: Mapped[dict] = mapped_column(JsonColumn, default=dict)
    complaint: Mapped[dict] = mapped_column(JsonColumn, default=dict)
    patient: Mapped[dict] = mapped_column(JsonColumn, default=dict)
    risk_assessment: Mapped[dict | None] = mapped_column(JsonColumn, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


Index("ix_complaints_owner", ComplaintRecord.owner_id)
