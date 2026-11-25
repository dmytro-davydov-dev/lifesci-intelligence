"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EMBEDDING_DIMENSIONS = 1536


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = "postgresql+psycopg://lifesci:lifesci@127.0.0.1:5432/lifesci"
    model_provider: Literal["fake", "openai", "gemini"] = "fake"
    openai_api_key: SecretStr | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str | None = None
    max_output_tokens: int = 1000
    retrieval_top_k: int = Field(default=8, ge=1, le=50)
    retrieval_mode: Literal["vector", "hybrid"] = "hybrid"
    retrieval_candidate_pool: int = Field(default=20, ge=1, le=200)
    rrf_k: int = Field(default=60, ge=1)
    context_max_tokens: int = 6000
    history_max_messages: int = Field(default=6, ge=0)
    history_message_max_chars: int = Field(default=2000, ge=100)
    request_deadline_seconds: float = Field(default=45.0, ge=5)
    # Comparison agent budgets (model-selected read-only tools).
    agent_max_steps: int = Field(default=6, ge=1, le=12)
    agent_max_searches: int = Field(default=3, ge=1, le=6)
    agent_results_per_search: int = Field(default=4, ge=1, le=20)
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 2
    # Google Gemini (MODEL_PROVIDER=gemini); embeddings are truncated to EMBEDDING_DIMENSIONS.
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-flash-lite-latest"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_seconds: float = 30.0
    gemini_max_retries: int = 2
    embedding_batch_size: int = 64
    ingestion_deadline_seconds: float = 120.0
    cors_origins: list[str] = ["http://127.0.0.1:3000", "http://localhost:3000"]
    db_connect_timeout_seconds: int = 3
    storage_dir: Path = Path("storage")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Optional LangSmith tracing; off by default and never required for tests.
    # Deliberately not the standard LANGSMITH_* names: those also switch on LangChain/LangGraph
    # auto-tracing of full prompts and outputs, which would bypass the redaction policy.
    trace_langsmith: bool = False
    trace_langsmith_api_key: SecretStr | None = None
    trace_langsmith_project: str = "lifesci-intelligence"
    trace_langsmith_endpoint: str | None = None
    # Adds question/answer/source text to traces. Approved public/synthetic data only.
    trace_include_content: bool = False

    @model_validator(mode="after")
    def _pool_covers_top_k(self) -> "Settings":
        if self.retrieval_candidate_pool < self.retrieval_top_k:
            raise ValueError("RETRIEVAL_CANDIDATE_POOL must be >= RETRIEVAL_TOP_K")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
