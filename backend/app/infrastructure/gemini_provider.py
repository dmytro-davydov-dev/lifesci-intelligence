"""Google Gemini model adapters over the Generative Language REST API (v1beta).

Chat:       POST {base}/models/{model}:generateContent
Embeddings: POST {base}/models/{model}:batchEmbedContents

The API key travels in the `x-goog-api-key` header, never in the URL, so it cannot leak
through logged URLs or exception messages.
"""

import logging
import math
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.config import EMBEDDING_DIMENSIONS
from app.domain.providers import ChatError, ChatMessage, EmbeddingError, ModelTimeoutError

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_NON_RETRYABLE_STATUS = {400, 401, 403, 404, 422}
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
# Deadline-bound calls get one quick retry on 503 (overloaded), only if enough budget remains.
# 429 is not retried here: a 1 s pause rarely clears a rate limit and would spend more quota.
_OVERLOAD_STATUS = {503}
_DEADLINE_RETRY_DELAY = 1.0
_MIN_DEADLINE_RETRY_BUDGET = 5.0
_BLOCKED_FINISH = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "LANGUAGE"}

logger = logging.getLogger("app.model")


class _ProviderHTTPError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status


class GeminiClient:
    """Minimal JSON-over-HTTP client with bounded retries."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            timeout=timeout,
            transport=transport,
        )
        self._timeout = timeout
        self._max_retries = max_retries
        self._sleep = sleep
        self._clock = clock

    def post(self, model: str, method: str, body: dict, timeout: float | None) -> dict:
        """POST models/{model}:{method}.

        Without a deadline (`timeout` is None, e.g. ingestion): retry 429/5xx and timeouts up
        to `max_retries` with exponential backoff. With a deadline: retry once on 503
        (provider overloaded) after a short pause, only if at least 5 s of the budget remain;
        timeouts are not retried because the budget is already spent.
        """
        path = f"/models/{model}:{method}"
        if timeout is not None:
            return self._post_within(path, body, timeout)
        for attempt in range(1 + self._max_retries):
            last = attempt == self._max_retries
            try:
                response = self._http.post(path, json=body, timeout=self._timeout)
            except httpx.TimeoutException:
                if last:
                    raise
                self._sleep(0.5 * 2**attempt)
                continue
            if response.status_code in _RETRYABLE_STATUS and not last:
                self._sleep(0.5 * 2**attempt)
                continue
            return self._parse(response)
        raise AssertionError("unreachable")  # pragma: no cover

    def _post_within(self, path: str, body: dict, budget: float) -> dict:
        started = self._clock()
        response = self._http.post(path, json=body, timeout=min(budget, self._timeout))
        if response.status_code in _OVERLOAD_STATUS:
            remaining = budget - (self._clock() - started) - _DEADLINE_RETRY_DELAY
            if remaining >= _MIN_DEADLINE_RETRY_BUDGET:
                self._sleep(_DEADLINE_RETRY_DELAY)
                response = self._http.post(path, json=body, timeout=min(remaining, self._timeout))
        return self._parse(response)

    @staticmethod
    def _parse(response: httpx.Response) -> dict:
        if response.status_code >= 400:
            raise _ProviderHTTPError(response.status_code)
        return response.json()


def _safe_message(exc: Exception, action: str, retry_hint: str) -> str:
    if isinstance(exc, _ProviderHTTPError):
        if exc.status in _NON_RETRYABLE_STATUS:
            return (
                f"{action} was rejected by the provider (HTTP {exc.status}). "
                "Check the provider configuration."
            )
        return f"{action} failed (HTTP {exc.status}). {retry_hint}"
    return f"{action} failed ({type(exc).__name__}). {retry_hint}"


def _log_usage(kind: str, model: str, usage: dict | None) -> None:
    """Token counts only; never prompt or completion text."""
    if not usage:
        return
    logger.info(
        "model_usage",
        extra={
            "fields": {
                "kind": kind,
                "model": model,
                "prompt_tokens": usage.get("promptTokenCount"),
                "completion_tokens": usage.get("candidatesTokenCount"),
                "thoughts_tokens": usage.get("thoughtsTokenCount"),
                "total_tokens": usage.get("totalTokenCount"),
            }
        },
    )


def _l2_normalize(vector: list[float]) -> list[float]:
    # gemini-embedding-001 only normalizes its full 3072-dim output; truncated ones must be.
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


class GeminiEmbeddingProvider:
    def __init__(self, client: GeminiClient, model: str, dimensions: int = EMBEDDING_DIMENSIONS):
        self._client = client
        self._model = model
        self.dimensions = dimensions

    def embed(self, texts: list[str], timeout: float | None = None) -> list[list[float]]:
        body = {
            "requests": [
                {
                    "model": f"models/{self._model}",
                    "content": {"parts": [{"text": text}]},
                    "outputDimensionality": self.dimensions,
                }
                for text in texts
            ]
        }
        try:
            payload = self._client.post(self._model, "batchEmbedContents", body, timeout)
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError("Embedding request timed out (TimeoutException).") from exc
        except (httpx.HTTPError, _ProviderHTTPError, ValueError) as exc:
            raise EmbeddingError(
                _safe_message(exc, "Embedding request", "Retry the upload later.")
            ) from exc
        embeddings = payload.get("embeddings") if isinstance(payload, dict) else None
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise EmbeddingError("Embedding provider returned an unexpected result.")
        return [_l2_normalize(list(item.get("values") or [])) for item in embeddings]


class GeminiChatProvider:
    def __init__(self, client: GeminiClient, model: str, max_output_tokens: int = 1000) -> None:
        self._client = client
        self._model = model
        self._max_output_tokens = max_output_tokens

    def complete_json(
        self,
        messages: list[ChatMessage],
        schema_name: str,
        schema: dict,
        timeout: float | None = None,
    ) -> str:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        body: dict[str, Any] = {
            "contents": [
                {
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                }
                for m in messages
                if m.role != "system"
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
                "maxOutputTokens": self._max_output_tokens,
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        try:
            payload = self._client.post(self._model, "generateContent", body, timeout)
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError("Model request timed out (TimeoutException).") from exc
        except (httpx.HTTPError, _ProviderHTTPError, ValueError) as exc:
            raise ChatError(_safe_message(exc, "Model request", "Try again shortly.")) from exc
        _log_usage("chat", self._model, payload.get("usageMetadata"))
        return self._extract_text(payload)

    @staticmethod
    def _extract_text(payload: dict) -> str:
        if (payload.get("promptFeedback") or {}).get("blockReason"):
            raise ChatError("The model declined to answer this request.")
        candidates = payload.get("candidates") or []
        if not candidates:
            raise ChatError("The model returned no answer.")
        candidate = candidates[0]
        finish = candidate.get("finishReason")
        if finish == "MAX_TOKENS":
            raise ChatError(
                "Model output was truncated by the output token limit (MAX_OUTPUT_TOKENS)."
            )
        if finish in _BLOCKED_FINISH:
            raise ChatError("The model declined to answer this request.")
        parts = (candidate.get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))
