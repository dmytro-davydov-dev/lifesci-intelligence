"""OpenAI model adapters."""

from typing import Any

import openai

from app.config import EMBEDDING_DIMENSIONS
from app.domain.providers import ChatError, ChatMessage, EmbeddingError, ModelTimeoutError

_NON_RETRYABLE_STATUS = {400, 401, 403, 404, 422}


def _safe_message(exc: openai.OpenAIError, action: str, retry_hint: str) -> str:
    name = type(exc).__name__
    if isinstance(exc, openai.APIStatusError) and exc.status_code in _NON_RETRYABLE_STATUS:
        return f"{action} was rejected by the provider ({name}). Check the provider configuration."
    return f"{action} failed ({name}). {retry_hint}"


def _bounded(client: Any, timeout: float | None, max_timeout: float | None) -> Any:
    """Per-call client for deadline-bound requests, capped at the configured timeout.

    SDK retries are disabled because they (and Retry-After waits) would exceed the deadline.
    """
    if timeout is None:
        return client
    if max_timeout is not None:
        timeout = min(timeout, max_timeout)
    return client.with_options(timeout=timeout, max_retries=0)


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        client: Any,
        model: str,
        dimensions: int = EMBEDDING_DIMENSIONS,
        max_timeout: float | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self.dimensions = dimensions
        self._max_timeout = max_timeout

    def embed(self, texts: list[str], timeout: float | None = None) -> list[list[float]]:
        try:
            response = _bounded(self._client, timeout, self._max_timeout).embeddings.create(
                model=self._model, input=texts, dimensions=self.dimensions
            )
        except openai.APITimeoutError as exc:
            raise ModelTimeoutError("Embedding request timed out (APITimeoutError).") from exc
        except openai.OpenAIError as exc:
            raise EmbeddingError(
                _safe_message(exc, "Embedding request", "Retry the upload later.")
            ) from exc
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]


class OpenAIChatProvider:
    def __init__(
        self,
        client: Any,
        model: str,
        max_output_tokens: int = 1000,
        max_timeout: float | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._max_timeout = max_timeout

    def complete_json(
        self,
        messages: list[ChatMessage],
        schema_name: str,
        schema: dict,
        timeout: float | None = None,
    ) -> str:
        try:
            response = _bounded(self._client, timeout, self._max_timeout).chat.completions.create(
                model=self._model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": schema, "strict": True},
                },
                max_completion_tokens=self._max_output_tokens,
            )
        except openai.APITimeoutError as exc:
            raise ModelTimeoutError("Model request timed out (APITimeoutError).") from exc
        except openai.OpenAIError as exc:
            raise ChatError(_safe_message(exc, "Model request", "Try again shortly.")) from exc
        choice = response.choices[0]
        message = choice.message
        if getattr(choice, "finish_reason", None) == "length":
            raise ChatError(
                "Model output was truncated by the output token limit (MAX_OUTPUT_TOKENS)."
            )
        if getattr(message, "refusal", None):
            raise ChatError("The model declined to answer this request.")
        return message.content or ""
