"""Deterministic offline providers for tests and keyless local runs."""

import hashlib
import math

from app.config import EMBEDDING_DIMENSIONS
from app.domain.providers import ChatMessage


class FakeEmbeddingProvider:
    """Hash-based unit vectors: identical text -> identical vector, no network."""

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        values: list[float] = []
        counter = 0
        while len(values) < self.dimensions:
            digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            values.extend((byte - 127.5) / 127.5 for byte in digest)
            counter += 1
        vector = values[: self.dimensions]
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class FakeChatProvider:
    """Returns a fixed reply so workflows can be tested without a model."""

    def __init__(self, reply: str = "FAKE_RESPONSE") -> None:
        self.reply = reply
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages: list[ChatMessage]) -> str:
        self.calls.append(list(messages))
        return self.reply
