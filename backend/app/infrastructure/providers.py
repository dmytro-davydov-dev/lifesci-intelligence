"""Select model providers from settings."""

import logging

import openai

from app.config import Settings
from app.domain.providers import ChatProvider, EmbeddingProvider
from app.domain.tracing import NoopTracer, SafeTracer, Tracer
from app.infrastructure.fake_providers import ExtractiveChatProvider, FakeEmbeddingProvider
from app.infrastructure.gemini_provider import (
    GeminiChatProvider,
    GeminiClient,
    GeminiEmbeddingProvider,
)
from app.infrastructure.openai_provider import OpenAIChatProvider, OpenAIEmbeddingProvider

logger = logging.getLogger("app.tracing")


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


def _gemini_client(settings: Settings) -> GeminiClient:
    if settings.gemini_api_key is None or not settings.gemini_api_key.get_secret_value():
        raise ProviderConfigurationError("MODEL_PROVIDER=gemini requires GEMINI_API_KEY.")
    return GeminiClient(
        settings.gemini_api_key.get_secret_value(),
        base_url=settings.gemini_base_url,
        timeout=settings.gemini_timeout_seconds,
        max_retries=settings.gemini_max_retries,
    )


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.model_provider == "fake":
        return FakeEmbeddingProvider()
    if settings.model_provider == "gemini":
        return GeminiEmbeddingProvider(_gemini_client(settings), settings.gemini_embedding_model)
    return OpenAIEmbeddingProvider(
        _openai_client(settings),
        settings.openai_embedding_model,
        max_timeout=settings.openai_timeout_seconds,
    )


def build_chat_provider(settings: Settings) -> ChatProvider:
    if settings.model_provider == "fake":
        return ExtractiveChatProvider()
    if settings.model_provider == "gemini":
        if not settings.gemini_model:
            raise ProviderConfigurationError("MODEL_PROVIDER=gemini requires GEMINI_MODEL.")
        return GeminiChatProvider(
            _gemini_client(settings), settings.gemini_model, settings.max_output_tokens
        )
    if not settings.openai_chat_model:
        raise ProviderConfigurationError("MODEL_PROVIDER=openai requires OPENAI_CHAT_MODEL.")
    return OpenAIChatProvider(
        _openai_client(settings),
        settings.openai_chat_model,
        settings.max_output_tokens,
        max_timeout=settings.openai_timeout_seconds,
    )


def build_tracer(settings: Settings) -> Tracer:
    """LangSmith when enabled and keyed; otherwise a no-op. Never raises."""
    if not settings.trace_langsmith:
        return NoopTracer()
    secret = settings.trace_langsmith_api_key
    key = secret.get_secret_value() if secret else ""
    if not key:
        logger.warning("tracing_disabled", extra={"fields": {"reason": "missing_api_key"}})
        return NoopTracer()
    try:
        from langsmith import Client

        from app.infrastructure.langsmith_tracer import LangSmithTracer

        client = Client(
            api_url=settings.trace_langsmith_endpoint,
            api_key=key,
            timeout_ms=(2000, 5000),
            omit_traced_runtime_info=True,  # no platform/git metadata, no git subprocess
            tracing_error_callback=lambda exc: logger.warning(
                "trace_failed",
                extra={"fields": {"action": "upload", "error_class": type(exc).__name__}},
            ),
        )
        return SafeTracer(LangSmithTracer(client, settings.trace_langsmith_project))
    except Exception as exc:
        logger.warning(
            "tracing_disabled",
            extra={"fields": {"reason": "client_error", "error_class": type(exc).__name__}},
        )
        return NoopTracer()
