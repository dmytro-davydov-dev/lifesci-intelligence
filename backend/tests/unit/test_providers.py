from types import SimpleNamespace
from unittest.mock import patch

import httpx
import openai
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.domain.providers import ChatError, ChatMessage, EmbeddingError
from app.infrastructure.fake_providers import ExtractiveChatProvider, FakeEmbeddingProvider
from app.infrastructure.openai_provider import OpenAIChatProvider, OpenAIEmbeddingProvider
from app.infrastructure.providers import (
    ProviderConfigurationError,
    build_chat_provider,
    build_embedding_provider,
)


class StubEmbeddings:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response, self.error, self.calls = response, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def test_openai_adapter_orders_by_index_and_passes_model_and_dimensions() -> None:
    data = [SimpleNamespace(index=1, embedding=[0.2]), SimpleNamespace(index=0, embedding=[0.1])]
    embeddings = StubEmbeddings(response=SimpleNamespace(data=data))
    provider = OpenAIEmbeddingProvider(SimpleNamespace(embeddings=embeddings), "m", dimensions=1)

    assert provider.embed(["a", "b"]) == [[0.1], [0.2]]
    assert embeddings.calls == [{"model": "m", "input": ["a", "b"], "dimensions": 1}]


def test_openai_adapter_wraps_provider_errors_without_leaking_details() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    error = openai.APITimeoutError(request=request)
    provider = OpenAIEmbeddingProvider(SimpleNamespace(embeddings=StubEmbeddings(error=error)), "m")

    with pytest.raises(EmbeddingError, match=r"APITimeoutError"):
        provider.embed(["secret document text"])


def test_openai_adapter_reports_non_retryable_rejections() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    error = openai.AuthenticationError(
        "bad key", response=httpx.Response(401, request=request), body=None
    )
    provider = OpenAIEmbeddingProvider(SimpleNamespace(embeddings=StubEmbeddings(error=error)), "m")

    with pytest.raises(EmbeddingError) as info:
        provider.embed(["x"])
    assert "rejected" in str(info.value) and "Retry" not in str(info.value)


def test_factory_passes_timeout_and_retries_to_client() -> None:
    settings = Settings(
        model_provider="openai",
        openai_api_key=SecretStr("sk-test"),
        openai_timeout_seconds=7,
        openai_max_retries=1,
    )
    with patch("app.infrastructure.providers.openai.OpenAI") as client_class:
        build_embedding_provider(settings)
    client_class.assert_called_once_with(api_key="sk-test", timeout=7, max_retries=1)


def test_factory_defaults_to_fake_provider() -> None:
    assert isinstance(build_embedding_provider(Settings()), FakeEmbeddingProvider)


@pytest.mark.parametrize("key", [None, ""])
def test_factory_requires_key_for_openai(key: str | None) -> None:
    settings = Settings(model_provider="openai", openai_api_key=SecretStr(key) if key else key)
    with pytest.raises(ProviderConfigurationError):
        build_embedding_provider(settings)


def test_factory_builds_openai_provider_with_key() -> None:
    settings = Settings(model_provider="openai", openai_api_key=SecretStr("sk-test"))
    assert isinstance(build_embedding_provider(settings), OpenAIEmbeddingProvider)


class StubCompletions:
    def __init__(self, message=None, error: Exception | None = None, finish_reason="stop") -> None:
        self.message, self.error, self.calls = message, error, []
        self.finish_reason = finish_reason

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=self.message, finish_reason=self.finish_reason)]
        )


def chat_client(completions: StubCompletions) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_openai_chat_requests_strict_json_schema_with_output_cap() -> None:
    completions = StubCompletions(message=SimpleNamespace(content='{"a":1}', refusal=None))
    provider = OpenAIChatProvider(chat_client(completions), "model-x", max_output_tokens=123)

    result = provider.complete_json([ChatMessage("user", "hi")], "answer", {"type": "object"})

    assert result == '{"a":1}'
    [call] = completions.calls
    assert call["model"] == "model-x"
    assert call["max_completion_tokens"] == 123
    assert call["messages"] == [{"role": "user", "content": "hi"}]
    assert call["response_format"]["json_schema"] == {
        "name": "answer",
        "schema": {"type": "object"},
        "strict": True,
    }


def test_openai_chat_refusal_raises_chat_error() -> None:
    completions = StubCompletions(message=SimpleNamespace(content=None, refusal="no"))
    with pytest.raises(ChatError, match="declined"):
        OpenAIChatProvider(chat_client(completions), "m").complete_json([], "a", {})


def test_openai_chat_wraps_provider_errors() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    completions = StubCompletions(error=openai.APIConnectionError(request=request))
    with pytest.raises(ChatError, match="APIConnectionError"):
        OpenAIChatProvider(chat_client(completions), "m").complete_json([], "a", {})


def test_chat_factory_defaults_to_extractive_fake() -> None:
    assert isinstance(build_chat_provider(Settings()), ExtractiveChatProvider)


def test_chat_factory_requires_model_name_for_openai() -> None:
    settings = Settings(model_provider="openai", openai_api_key=SecretStr("sk-test"))
    with pytest.raises(ProviderConfigurationError, match="OPENAI_CHAT_MODEL"):
        build_chat_provider(settings)


def test_chat_factory_builds_openai_chat_provider() -> None:
    settings = Settings(
        model_provider="openai", openai_api_key=SecretStr("sk-test"), openai_chat_model="m"
    )
    assert isinstance(build_chat_provider(settings), OpenAIChatProvider)


def test_openai_chat_truncated_output_raises_distinct_error() -> None:
    completions = StubCompletions(
        message=SimpleNamespace(content='{"status": "ans', refusal=None), finish_reason="length"
    )
    with pytest.raises(ChatError, match="truncated"):
        OpenAIChatProvider(chat_client(completions), "m").complete_json([], "a", {})
