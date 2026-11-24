"""OpenAI model adapters."""

from typing import Any

import openai

from app.config import EMBEDDING_DIMENSIONS
from app.domain.providers import EmbeddingError

_NON_RETRYABLE_STATUS = {400, 401, 403, 404, 422}


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
        except openai.APIStatusError as exc:
            if exc.status_code in _NON_RETRYABLE_STATUS:
                raise EmbeddingError(
                    f"Embedding provider rejected the request ({type(exc).__name__}). "
                    "Check the provider configuration."
                ) from exc
            raise EmbeddingError(
                f"Embedding request failed ({type(exc).__name__}). Retry the upload later."
            ) from exc
        except openai.OpenAIError as exc:
            raise EmbeddingError(
                f"Embedding request failed ({type(exc).__name__}). Retry the upload later."
            ) from exc
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
