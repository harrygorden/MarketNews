"""
Application configuration using Pydantic settings.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized configuration loaded from environment variables and optional .env file.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = Field(
        ...,
        description="Async SQLAlchemy URL, e.g. postgresql+asyncpg://user:password@host:5432/db",
    )

    STOCKNEWS_API_KEY: str | None = Field(default=None, description="StockNewsAPI key")
    FIRECRAWL_API_KEY: str | None = Field(default=None, description="FireCrawl API key")

    OPENAI_API_KEY: str | None = Field(default=None, description="OpenAI API key")
    ANTHROPIC_API_KEY: str | None = Field(default=None, description="Anthropic API key")
    GOOGLE_AI_API_KEY: str | None = Field(default=None, description="Google AI API key")

    DISCORD_WEBHOOK_ALERTS: str | None = Field(default=None, description="Discord alerts webhook")
    DISCORD_WEBHOOK_DIGESTS: str | None = Field(default=None, description="Discord digests webhook")

    AZURE_STORAGE_CONNECTION_STRING: str | None = Field(
        default=None, description="Azure Storage connection string for queues"
    )

    IMPACT_THRESHOLD: float = Field(
        0.7, ge=0.0, le=1.0, description="Default impact threshold for high-signal alerts"
    )
    LOG_LEVEL: str = Field("INFO", description="Python logging level string")

    @field_validator("DATABASE_URL")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql"):
            raise ValueError("DATABASE_URL must start with 'postgresql'")
        if "+asyncpg" not in value:
            raise ValueError("DATABASE_URL must use the async driver, e.g. postgresql+asyncpg://")
        return value


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings accessor to avoid re-parsing environment variables.
    """

    return Settings()

