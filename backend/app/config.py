"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

EMBEDDING_DIMENSIONS = 1536


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = "postgresql+psycopg://lifesci:lifesci@127.0.0.1:5432/lifesci"
    model_provider: Literal["fake", "openai"] = "fake"
    openai_api_key: SecretStr | None = None
    openai_embedding_model: str = "text-embedding-3-small"
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
