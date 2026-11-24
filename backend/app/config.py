"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

EMBEDDING_DIMENSIONS = 1536


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = "postgresql+psycopg://lifesci:lifesci@127.0.0.1:5432/lifesci"
    model_provider: Literal["fake", "openai"] = "fake"
    openai_api_key: SecretStr | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str | None = None
    max_output_tokens: int = 1000
    retrieval_top_k: int = 8
    context_max_tokens: int = 6000
    history_max_messages: int = Field(default=6, ge=0)
    history_message_max_chars: int = Field(default=2000, ge=100)
    request_deadline_seconds: float = Field(default=45.0, ge=5)
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 2
    embedding_batch_size: int = 64
    ingestion_deadline_seconds: float = 120.0
    cors_origins: list[str] = ["http://127.0.0.1:3000", "http://localhost:3000"]
    db_connect_timeout_seconds: int = 3
    storage_dir: Path = Path("storage")


@lru_cache
def get_settings() -> Settings:
    return Settings()
