"""Deterministic offline providers for tests and keyless local runs."""

import hashlib
import math
import re

from app.config import EMBEDDING_DIMENSIONS
from app.domain.providers import ChatMessage

_TOKEN = re.compile(r"[a-z0-9]+")


class FakeEmbeddingProvider:
    """Hashed bag-of-words unit vectors: texts sharing terms are similar. No network.

    Useful for deterministic retrieval tests; not a semantic model.
    """

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            vector[0], norm = 1.0, 1.0
        return [v / norm for v in vector]


class FakeChatProvider:
    """Returns a fixed reply so workflows can be tested without a model."""

    def __init__(self, reply: str = "FAKE_RESPONSE") -> None:
        self.reply = reply
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages: list[ChatMessage]) -> str:
        self.calls.append(list(messages))
        return self.reply
