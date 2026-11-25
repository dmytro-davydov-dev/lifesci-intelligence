import json
import math

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.domain.providers import ChatError, ChatMessage, EmbeddingError, ModelTimeoutError
from app.infrastructure.gemini_provider import (
    GeminiChatProvider,
    GeminiClient,
    GeminiEmbeddingProvider,
)
from app.infrastructure.providers import (
    ProviderConfigurationError,
    build_chat_provider,
    build_embedding_provider,
)

KEY = "gm-test-key"


class Recorder:
    """httpx transport that replays queued responses and records requests."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def body(self, index: int = 0) -> dict:
        return json.loads(self.requests[index].content)


def client(recorder: Recorder, **kwargs) -> GeminiClient:
    return GeminiClient(
        KEY, transport=httpx.MockTransport(recorder), sleep=lambda _: None, **kwargs
    )


def answer(text: str, finish: str = "STOP", **extra) -> httpx.Response:
    candidate = {"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": finish}
    return httpx.Response(200, json={"candidates": [candidate], **extra})


MESSAGES = [
    ChatMessage("system", "Answer from sources only."),
    ChatMessage("user", "Earlier question"),
    ChatMessage("assistant", "Earlier answer"),
    ChatMessage("user", "How soon must a deviation be recorded?"),
]


def test_chat_posts_generate_content_with_schema_and_key_in_header_only() -> None:
    recorder = Recorder(answer('{"status":"answered"}'))
    provider = GeminiChatProvider(client(recorder), "gemini-flash-lite-latest", 321)

    result = provider.complete_json(MESSAGES, "answer", {"type": "object"})

    assert result == '{"status":"answered"}'
    [request] = recorder.requests
    assert str(request.url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-flash-lite-latest:generateContent"
    )
    assert request.headers["x-goog-api-key"] == KEY
    assert KEY not in str(request.url)
    assert recorder.body() == {
        "systemInstruction": {"parts": [{"text": "Answer from sources only."}]},
        "contents": [
            {"role": "user", "parts": [{"text": "Earlier question"}]},
            {"role": "model", "parts": [{"text": "Earlier answer"}]},
            {"role": "user", "parts": [{"text": "How soon must a deviation be recorded?"}]},
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": {"type": "object"},
            "maxOutputTokens": 321,
        },
    }


def test_chat_skips_thought_parts_and_joins_text_parts() -> None:
    parts = [{"text": "thinking...", "thought": True}, {"text": '{"a":'}, {"text": "1}"}]
    payload = {"candidates": [{"content": {"parts": parts}, "finishReason": "STOP"}]}
    provider = GeminiChatProvider(client(Recorder(httpx.Response(200, json=payload))), "m")

    assert provider.complete_json([ChatMessage("user", "q")], "s", {}) == '{"a":1}'


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (answer("{", finish="MAX_TOKENS"), "MAX_OUTPUT_TOKENS"),
        (answer("", finish="SAFETY"), "declined"),
        (httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}), "declined"),
        (httpx.Response(200, json={"candidates": []}), "no answer"),
    ],
)
def test_chat_maps_unusable_responses_to_safe_errors(response, message) -> None:
    provider = GeminiChatProvider(client(Recorder(response)), "m")
    with pytest.raises(ChatError, match=message):
        provider.complete_json([ChatMessage("user", "q")], "s", {})


def test_chat_rejection_message_is_safe_and_never_retried() -> None:
    recorder = Recorder(httpx.Response(400, json={"error": {"message": f"bad key {KEY}"}}))
    provider = GeminiChatProvider(client(recorder), "m")

    with pytest.raises(ChatError) as info:
        provider.complete_json([ChatMessage("user", "secret document text")], "s", {})

    assert "rejected by the provider (HTTP 400)" in str(info.value)
    assert KEY not in str(info.value) and "secret" not in str(info.value)
    assert len(recorder.requests) == 1


def test_deadline_bound_call_times_out_without_retry() -> None:
    recorder = Recorder(httpx.ReadTimeout("slow"))
    provider = GeminiChatProvider(client(recorder, timeout=30), "m")

    with pytest.raises(ModelTimeoutError):
        provider.complete_json([ChatMessage("user", "q")], "s", {}, timeout=2)
    assert len(recorder.requests) == 1
    assert recorder.requests[0].extensions["timeout"]["read"] == 2


class FakeClock:
    def __init__(self, *readings: float) -> None:
        self.readings = list(readings)

    def __call__(self) -> float:
        return self.readings.pop(0)


def test_deadline_bound_call_retries_overload_once_within_remaining_budget() -> None:
    recorder = Recorder(httpx.Response(503), answer('{"ok":true}'))
    sleeps: list[float] = []
    gemini = GeminiClient(
        KEY,
        transport=httpx.MockTransport(recorder),
        sleep=sleeps.append,
        clock=FakeClock(100.0, 102.0),
    )

    result = GeminiChatProvider(gemini, "m").complete_json([ChatMessage("user", "q")], "s", {}, 20)

    assert result == '{"ok":true}'
    assert sleeps == [1.0]
    timeouts = [r.extensions["timeout"]["read"] for r in recorder.requests]
    assert timeouts == [20, 17.0]  # 20 s budget - 2 s first attempt - 1 s pause


@pytest.mark.parametrize(
    ("first", "elapsed"),
    [
        (httpx.Response(503), 15.0),
        (httpx.Response(429), 0.0),
        (httpx.Response(500), 0.0),
        (httpx.Response(400), 0.0),
    ],
)
def test_deadline_bound_call_does_not_retry_without_budget_or_on_other_errors(
    first: httpx.Response, elapsed: float
) -> None:
    recorder = Recorder(first)
    gemini = GeminiClient(
        KEY,
        transport=httpx.MockTransport(recorder),
        sleep=lambda _: None,
        clock=FakeClock(0.0, elapsed),
    )

    with pytest.raises(ChatError, match=f"HTTP {first.status_code}"):
        GeminiChatProvider(gemini, "m").complete_json([ChatMessage("user", "q")], "s", {}, 20)
    assert len(recorder.requests) == 1


def test_calls_without_deadline_retry_transient_failures() -> None:
    recorder = Recorder(httpx.Response(429), httpx.ReadTimeout("slow"), answer('{"ok":true}'))
    provider = GeminiChatProvider(client(recorder, max_retries=2), "m")

    assert provider.complete_json([ChatMessage("user", "q")], "s", {}) == '{"ok":true}'
    assert len(recorder.requests) == 3


def test_retries_are_bounded() -> None:
    recorder = Recorder(httpx.Response(503), httpx.Response(503))
    provider = GeminiChatProvider(client(recorder, max_retries=1), "m")

    with pytest.raises(ChatError, match=r"HTTP 503"):
        provider.complete_json([ChatMessage("user", "q")], "s", {})
    assert len(recorder.requests) == 2


def test_embeddings_batch_request_truncates_dimensions_and_normalizes() -> None:
    payload = {"embeddings": [{"values": [3.0, 4.0]}, {"values": [0.0, 2.0]}]}
    recorder = Recorder(httpx.Response(200, json=payload))
    provider = GeminiEmbeddingProvider(client(recorder), "gemini-embedding-001", dimensions=2)

    vectors = provider.embed(["a", "b"])

    assert vectors == [[0.6, 0.8], [0.0, 1.0]]
    assert all(math.isclose(math.hypot(*v), 1.0) for v in vectors)
    assert recorder.requests[0].url.path.endswith("/models/gemini-embedding-001:batchEmbedContents")
    assert recorder.body() == {
        "requests": [
            {
                "model": "models/gemini-embedding-001",
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": 2,
            }
            for text in ["a", "b"]
        ]
    }


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"embeddings": [{"values": [1.0]}]}),
        httpx.Response(200, json={"unexpected": True}),
        httpx.Response(401),
    ],
)
def test_embedding_failures_raise_embedding_error(response) -> None:
    provider = GeminiEmbeddingProvider(client(Recorder(response)), "m", dimensions=1)
    with pytest.raises(EmbeddingError):
        provider.embed(["a", "b"])


def test_embedding_timeout_is_model_timeout() -> None:
    provider = GeminiEmbeddingProvider(client(Recorder(httpx.ConnectTimeout("x"))), "m")
    with pytest.raises(ModelTimeoutError):
        provider.embed(["a"], timeout=1)


def test_factory_builds_gemini_providers_with_default_models() -> None:
    settings = Settings(model_provider="gemini", gemini_api_key=SecretStr(KEY))

    chat = build_chat_provider(settings)
    embedder = build_embedding_provider(settings)

    assert isinstance(chat, GeminiChatProvider) and chat._model == "gemini-flash-lite-latest"
    assert isinstance(embedder, GeminiEmbeddingProvider)
    assert embedder._model == "gemini-embedding-001" and embedder.dimensions == 1536


def test_gemini_model_comes_from_settings() -> None:
    settings = Settings(
        model_provider="gemini", gemini_api_key=SecretStr(KEY), gemini_model="gemini-2.5-pro"
    )
    assert build_chat_provider(settings)._model == "gemini-2.5-pro"


@pytest.mark.parametrize("key", [None, ""])
def test_factory_requires_gemini_key(key: str | None) -> None:
    settings = Settings(model_provider="gemini", gemini_api_key=SecretStr(key) if key else key)
    with pytest.raises(ProviderConfigurationError, match="GEMINI_API_KEY"):
        build_chat_provider(settings)
    with pytest.raises(ProviderConfigurationError, match="GEMINI_API_KEY"):
        build_embedding_provider(settings)
