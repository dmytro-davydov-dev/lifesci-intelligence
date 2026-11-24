"""Model provider interfaces. Kept framework- and vendor-free."""

from dataclasses import dataclass
from typing import Literal, Protocol


class EmbeddingError(Exception):
    """Provider failure with a message that is safe to show to users."""


class EmbeddingProvider(Protocol):
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding per input text, in order."""
        ...


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


class ChatError(Exception):
    """Chat provider failure with a message that is safe to show to users."""


class ChatProvider(Protocol):
    def complete_json(self, messages: list[ChatMessage], schema_name: str, schema: dict) -> str:
        """Return a JSON string conforming to the given schema."""
        ...
