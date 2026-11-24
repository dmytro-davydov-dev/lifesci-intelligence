import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.application.ingestion import IngestionService
from app.domain.chunking import ChunkDraft
from app.domain.providers import EmbeddingError
from app.infrastructure.fake_providers import FakeEmbeddingProvider


class RecordingEmbedder(FakeEmbeddingProvider):
    def __init__(self, drop_one: bool = False) -> None:
        super().__init__(dimensions=4)
        self.batches: list[list[str]] = []
        self.drop_one = drop_one

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(texts)
        vectors = super().embed(texts)
        return vectors[:-1] if self.drop_one else vectors


def service(embedder, **kwargs) -> IngestionService:
    session_factory = MagicMock()

    @contextmanager
    def begin():
        yield MagicMock()

    session_factory.begin.side_effect = begin
    return IngestionService(session_factory, embedder, **kwargs)


def test_embeds_in_batches_preserving_order() -> None:
    embedder = RecordingEmbedder()
    vectors = service(embedder, batch_size=2)._embed(["a", "b", "c"])

    assert embedder.batches == [["a", "b"], ["c"]]
    assert vectors == FakeEmbeddingProvider(dimensions=4).embed(["a", "b", "c"])


def test_rejects_batch_count_mismatch() -> None:
    with pytest.raises(EmbeddingError, match="unexpected result"):
        service(RecordingEmbedder(drop_one=True))._embed(["a", "b"])


def test_stops_when_deadline_exceeded_between_batches() -> None:
    times = iter([0.0, 0.0, 200.0])
    embedder = RecordingEmbedder()
    svc = service(embedder, batch_size=1, deadline_seconds=120, clock=lambda: next(times))

    with pytest.raises(EmbeddingError, match="too long"):
        svc._embed(["a", "b", "c"])
    assert embedder.batches == [["a"]]


def test_ingest_marks_failed_with_error_class_only() -> None:
    svc = service(RecordingEmbedder(drop_one=True))
    with patch.object(svc, "_mark_failed", return_value="failed-doc") as mark_failed:
        result = svc.ingest(uuid.uuid4(), [ChunkDraft(0, None, None, "secret text")])

    assert result == "failed-doc"
    _, message, error_class = mark_failed.call_args.args
    assert "secret text" not in message
    assert error_class == "EmbeddingError"
