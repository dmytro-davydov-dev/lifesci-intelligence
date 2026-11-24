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


class ChatProvider(Protocol):
    def complete(self, messages: list[ChatMessage]) -> str:
        """Return the model's text completion for the given messages."""
        ...
