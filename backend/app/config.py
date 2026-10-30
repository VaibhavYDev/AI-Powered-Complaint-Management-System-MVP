import re

from pydantic import AliasChoices, Field, field_validator, model_validator
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
    # A single inference must not be able to hold a worker open indefinitely.
    llm_timeout_seconds: float = 45.0
    llm_max_retries: int = 3
    db_connect_timeout: int = 5
    health_cache_seconds: float = 5.0
    # Which revision is actually serving. Render sets RENDER_GIT_COMMIT on every build; any other
    # platform can set GIT_COMMIT. Reported by /api/health so a deployment can be identified from
    # outside instead of inferred from what the page happens to contain.
    git_commit: str = Field("", validation_alias=AliasChoices("GIT_COMMIT", "RENDER_GIT_COMMIT"))
    max_pdf_pages: int = 50
    max_pdf_seconds: float = 15.0

    # Sessions. SESSION_SECRET must be set in any deployment that runs more than one
    # instance or expects sessions to survive a restart.
    # "production" refuses to start without a stable session secret and Secure cookies.
    environment: str = "development"
    session_secret: str = ""
    session_max_age: int = 14 * 24 * 3600
    secure_cookies: bool = False
    ai_rate_limit: int = 30
    ai_rate_window: float = 60.0
    session_rate_limit: int = 20
    session_rate_window: float = 3600.0

    @model_validator(mode="after")
    def _production_must_be_hardened(self):
        if self.environment == "production":
            missing = [
                name
                for name, ok in (("SESSION_SECRET", bool(self.session_secret)), ("SECURE_COOKIES=true", self.secure_cookies))
                if not ok
            ]
            if missing:
                raise ValueError(f"ENVIRONMENT=production requires {' and '.join(missing)}")
        return self

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, url: str) -> str:
        # Hosted PostgreSQL (e.g. Render) hands out postgres:// or postgresql:// URLs; SQLAlchemy
        # would look for psycopg2, so name the installed psycopg (v3) driver explicitly.
        return re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", url)


settings = Settings()
