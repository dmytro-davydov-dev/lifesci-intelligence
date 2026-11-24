"""OpenAI model adapters."""

from typing import Any

import openai

from app.config import EMBEDDING_DIMENSIONS
from app.domain.providers import ChatError, ChatMessage, EmbeddingError

_NON_RETRYABLE_STATUS = {400, 401, 403, 404, 422}


def _safe_message(exc: openai.OpenAIError, action: str, retry_hint: str) -> str:
    name = type(exc).__name__
    if isinstance(exc, openai.APIStatusError) and exc.status_code in _NON_RETRYABLE_STATUS:
        return f"{action} was rejected by the provider ({name}). Check the provider configuration."
    return f"{action} failed ({name}). {retry_hint}"


class OpenAIEmbeddingProvider:
    def __init__(self, client: Any, model: str, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self._client = client
        self._model = model
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(
                model=self._model, input=texts, dimensions=self.dimensions
            )
        except openai.OpenAIError as exc:
            raise EmbeddingError(
                _safe_message(exc, "Embedding request", "Retry the upload later.")
            ) from exc
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]


class OpenAIChatProvider:
    def __init__(self, client: Any, model: str, max_output_tokens: int = 1000) -> None:
        self._client = client
        self._model = model
        self._max_output_tokens = max_output_tokens

    def complete_json(self, messages: list[ChatMessage], schema_name: str, schema: dict) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": schema, "strict": True},
                },
                max_completion_tokens=self._max_output_tokens,
            )
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
