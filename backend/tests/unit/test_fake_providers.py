import math

from app.config import EMBEDDING_DIMENSIONS
from app.domain.providers import ChatMessage
from app.infrastructure.fake_providers import FakeChatProvider, FakeEmbeddingProvider


def test_fake_embeddings_are_deterministic_unit_vectors() -> None:
    provider = FakeEmbeddingProvider()
    first, second, other = provider.embed(["deviation report", "deviation report", "CAPA"])

    assert len(first) == EMBEDDING_DIMENSIONS
    assert first == second
    assert first != other
    assert math.isclose(math.fsum(v * v for v in first), 1.0, rel_tol=1e-9)


def test_fake_embeddings_rank_shared_terms_higher() -> None:
    provider = FakeEmbeddingProvider()
    query, related, unrelated = provider.embed(
        ["when must deviations be reported", "Deviations must be reported within 24 hours", "x y z"]
    )

    def cosine(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert cosine(query, related) > cosine(query, unrelated)


def test_fake_embeddings_handle_text_without_tokens() -> None:
    assert math.isclose(math.fsum(v * v for v in FakeEmbeddingProvider().embed(["  "])[0]), 1.0)


def test_fake_embeddings_preserve_input_order_and_count() -> None:
    provider = FakeEmbeddingProvider(dimensions=8)
    texts = ["a", "b", "c"]
    assert provider.embed(texts) == [provider.embed([t])[0] for t in texts]


def test_fake_chat_returns_reply_and_records_messages() -> None:
    provider = FakeChatProvider(reply="hello")
    messages = [ChatMessage(role="user", content="hi")]
    assert provider.complete(messages) == "hello"
    assert provider.calls == [messages]
