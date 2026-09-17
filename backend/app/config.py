from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://aivoa:aivoa@localhost:5432/aivoa"
    groq_api_key: str = ""
    groq_model: str = "gemma2-9b-it"
    # Assignment model first; Groq deprecated gemma2-9b-it on 2025-10-08, so a fallback is
    # resolved at startup (see ai/llm.py). llama-3.3-70b-versatile is a valid choice for either.
    groq_fallback_model: str = "llama-3.1-8b-instant"
    frontend_url: str = "http://localhost:5173"
    max_upload_bytes: int = 10 * 1024 * 1024
    max_document_chars: int = 12_000


settings = Settings()
