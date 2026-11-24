"""Embed chunks and publish them atomically with the document's ready status."""

import logging
import time
import uuid
from collections.abc import Callable

from sqlalchemy.orm import sessionmaker

from app.domain.chunking import ChunkDraft
from app.domain.providers import EmbeddingError, EmbeddingProvider
from app.infrastructure.document_repository import DocumentRepository
from app.infrastructure.models import Document

logger = logging.getLogger("app.ingestion")


class IngestionService:
    def __init__(
        self,
        session_factory: sessionmaker,
        embedder: EmbeddingProvider,
        batch_size: int = 64,
        deadline_seconds: float = 120.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_factory = session_factory
        self._embedder = embedder
        self._batch_size = batch_size
        self._deadline_seconds = deadline_seconds
        self._clock = clock

    def ingest(self, document_id: uuid.UUID, drafts: list[ChunkDraft]) -> Document:
        """Embed and persist chunks; on any failure mark the document failed, keep no chunks."""
        started = time.monotonic()
        try:
            vectors = self._embed([draft.text for draft in drafts])
            with self._session_factory.begin() as session:
                repository = DocumentRepository(session)
                repository.replace_chunks(document_id, drafts, vectors)
                document = repository.set_status(document_id, "ready", None)
        except EmbeddingError as exc:
            return self._mark_failed(document_id, str(exc), type(exc).__name__)
        except Exception as exc:
            message = f"Ingestion failed ({type(exc).__name__}). Retry the upload."
            return self._mark_failed(document_id, message, type(exc).__name__)
        logger.info(
            "document_ingested document_id=%s chunks=%d duration_ms=%d",
            document_id,
            len(drafts),
            (time.monotonic() - started) * 1000,
        )
        return document

    def claim_failed(self, document_id: uuid.UUID) -> bool:
        with self._session_factory.begin() as session:
            return DocumentRepository(session).claim_failed(document_id)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        deadline = self._clock() + self._deadline_seconds
        for offset in range(0, len(texts), self._batch_size):
            # Checked between batches; a single in-flight call is bounded by the provider timeout.
            if self._clock() > deadline:
                raise EmbeddingError("Embedding took too long. Retry with a smaller document.")
            batch = texts[offset : offset + self._batch_size]
            result = self._embedder.embed(batch)
            if len(result) != len(batch) or any(
                len(vector) != self._embedder.dimensions for vector in result
            ):
                raise EmbeddingError("Embedding provider returned an unexpected result.")
            vectors.extend(result)
        return vectors

    def _mark_failed(self, document_id: uuid.UUID, message: str, error_class: str) -> Document:
        # Log the error class only: provider/DB messages may echo document text.
        logger.warning(
            "document_ingestion_failed document_id=%s error_class=%s", document_id, error_class
        )
        with self._session_factory.begin() as session:
            return DocumentRepository(session).set_status(document_id, "failed", message)
