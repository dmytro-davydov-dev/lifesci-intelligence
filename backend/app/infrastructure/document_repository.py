"""Persistence for document metadata."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Document


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, document_id: uuid.UUID) -> Document | None:
        return self.session.get(Document, document_id)

    def get_by_sha256(self, sha256: str) -> Document | None:
        return self.session.scalars(select(Document).where(Document.sha256 == sha256)).first()

    def list(self) -> list[Document]:
        return list(self.session.scalars(select(Document).order_by(Document.created_at.desc())))

    def add(self, document: Document) -> Document:
        self.session.add(document)
        self.session.flush()
        return document
