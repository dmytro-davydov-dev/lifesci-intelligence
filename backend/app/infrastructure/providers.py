"""Select model providers from settings."""

import openai

from app.config import Settings
from app.domain.providers import EmbeddingProvider
from app.infrastructure.fake_providers import FakeEmbeddingProvider
from app.infrastructure.openai_provider import OpenAIEmbeddingProvider


class ProviderConfigurationError(RuntimeError):
    pass


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.model_provider == "fake":
        return FakeEmbeddingProvider()
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        raise ProviderConfigurationError("MODEL_PROVIDER=openai requires OPENAI_API_KEY.")
    client = openai.OpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    return OpenAIEmbeddingProvider(client, settings.openai_embedding_model)
