from types import SimpleNamespace
from unittest.mock import patch

import httpx
import openai
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.domain.providers import EmbeddingError
from app.infrastructure.fake_providers import FakeEmbeddingProvider
from app.infrastructure.openai_provider import OpenAIEmbeddingProvider
from app.infrastructure.providers import ProviderConfigurationError, build_embedding_provider


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
