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
    frontend_url: str = "http://localhost:5173"
    max_upload_bytes: int = 10 * 1024 * 1024
    max_document_chars: int = 12_000


settings = Settings()
