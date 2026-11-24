"""Select model providers from settings."""

import openai

from app.config import Settings
from app.domain.providers import ChatProvider, EmbeddingProvider
from app.infrastructure.fake_providers import ExtractiveChatProvider, FakeEmbeddingProvider
from app.infrastructure.openai_provider import OpenAIChatProvider, OpenAIEmbeddingProvider


class ProviderConfigurationError(RuntimeError):
    pass


def _openai_client(settings: Settings) -> openai.OpenAI:
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        raise ProviderConfigurationError("MODEL_PROVIDER=openai requires OPENAI_API_KEY.")
    return openai.OpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.model_provider == "fake":
        return FakeEmbeddingProvider()
    return OpenAIEmbeddingProvider(
        _openai_client(settings),
        settings.openai_embedding_model,
        max_timeout=settings.openai_timeout_seconds,
    )


def build_chat_provider(settings: Settings) -> ChatProvider:
    if settings.model_provider == "fake":
        return ExtractiveChatProvider()
    if not settings.openai_chat_model:
        raise ProviderConfigurationError("MODEL_PROVIDER=openai requires OPENAI_CHAT_MODEL.")
    return OpenAIChatProvider(
        _openai_client(settings),
        settings.openai_chat_model,
        settings.max_output_tokens,
        max_timeout=settings.openai_timeout_seconds,
    )
