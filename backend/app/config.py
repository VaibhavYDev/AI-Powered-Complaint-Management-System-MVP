from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://aivoa:aivoa@localhost:5432/aivoa"
    groq_api_key: str = ""
    groq_model: str = "gemma2-9b-it"
    # Used automatically if Groq reports the configured model as decommissioned/unknown.
    groq_fallback_model: str = "llama-3.3-70b-versatile"
    frontend_url: str = "http://localhost:5173"
    max_upload_bytes: int = 10 * 1024 * 1024
    max_document_chars: int = 12_000


settings = Settings()
