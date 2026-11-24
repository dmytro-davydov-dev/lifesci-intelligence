"""Persistence for documents and their chunks."""

import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.domain.chunking import ChunkDraft
from app.infrastructure.models import Chunk, Document


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, document_id: uuid.UUID) -> Document | None:
        return self.session.get(Document, document_id)

    def get_by_sha256(self, sha256: str) -> Document | None:
        return self.session.scalars(select(Document).where(Document.sha256 == sha256)).first()

    def list_all(self) -> list[Document]:
        return list(self.session.scalars(select(Document).order_by(Document.created_at.desc())))

    def add(self, document: Document) -> Document:
        self.session.add(document)
        self.session.flush()
        return document

    def set_status(self, document_id: uuid.UUID, status: str, error: str | None) -> Document:
        document = self.session.get(Document, document_id, with_for_update=True)
        if document is None:
            raise LookupError(str(document_id))
        document.status = status
        document.error = error
        self.session.flush()
        return document

    def claim_failed(self, document_id: uuid.UUID) -> bool:
        """Atomically move a failed document back to processing; False if not failed."""
        result = self.session.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == "failed")
            .values(status="processing", error=None)
        )
        return result.rowcount == 1

    def replace_chunks(
        self, document_id: uuid.UUID, drafts: list[ChunkDraft], vectors: list[list[float]]
    ) -> None:
        self.session.execute(delete(Chunk).where(Chunk.document_id == document_id))
        self.session.add_all(
            Chunk(
                document_id=document_id,
                ordinal=draft.ordinal,
                page=draft.page,
                section=draft.section,
                text=draft.text,
                embedding=vector,
            )
            for draft, vector in zip(drafts, vectors, strict=True)
        )
        self.session.flush()

    def get_chunk(self, document_id: uuid.UUID, chunk_id: uuid.UUID) -> Chunk | None:
        return self.session.scalars(
            select(Chunk).where(Chunk.id == chunk_id, Chunk.document_id == document_id)
        ).first()

    def count_chunks(self, document_id: uuid.UUID) -> int:
        return self.session.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
        )
