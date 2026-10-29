import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://aivoa:aivoa@localhost:5432/aivoa"
    groq_api_key: str = ""
    # The assignment model. Groq shut it down on 2025-10-08, so ai/llm.py checks it at startup
    # and falls back to a currently supported model; /api/health reports which one is active.
    groq_model: str = "gemma2-9b-it"
    # Current Groq production model. openai/gpt-oss-120b is the larger option.
    # (llama-3.1-8b-instant / llama-3.3-70b-versatile were shut down for free/dev tiers on 2026-08-16.)
    groq_fallback_model: str = "openai/gpt-oss-20b"
    # gpt-oss reasoning effort (low|medium|high). Low keeps free-tier token budgets in check.
    groq_reasoning_effort: str = "low"
    frontend_url: str = "http://localhost:5173"
    max_upload_bytes: int = 10 * 1024 * 1024
    max_document_chars: int = 12_000
    max_pdf_pages: int = 50
    max_pdf_seconds: float = 15.0

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, url: str) -> str:
        # Hosted PostgreSQL (e.g. Render) hands out postgres:// or postgresql:// URLs; SQLAlchemy
        # would look for psycopg2, so name the installed psycopg (v3) driver explicitly.
        return re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", url)


settings = Settings()
