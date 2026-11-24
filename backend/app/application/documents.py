"""Document upload and lookup use cases."""

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.application.ingestion import IngestionService
from app.domain.chunking import ChunkDraft, PageText, chunk_pages
from app.domain.documents import (
    PDF_MEDIA_TYPE,
    ValidatedUpload,
    check_extractable_text,
    validate_upload,
)
from app.infrastructure.document_repository import DocumentRepository
from app.infrastructure.models import Chunk, Document
from app.infrastructure.storage import LocalFileStorage

PdfReader = Callable[[bytes], list[PageText]]


class DocumentNotFoundError(Exception):
    pass


class ChunkNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class UploadResult:
    document: Document
    duplicate: bool


class DocumentService:
    def __init__(
        self,
        session_factory: sessionmaker,
        storage: LocalFileStorage,
        read_pdf_pages: PdfReader,
        ingestion: IngestionService,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._read_pdf_pages = read_pdf_pages
        self._ingestion = ingestion

    def upload(self, filename: str | None, data: bytes) -> UploadResult:
        upload = validate_upload(filename, data)
        sha256 = hashlib.sha256(data).hexdigest()

        existing = self._find_by_sha256(sha256)
        if existing is not None:
            if existing.status == "failed":
                drafts = self._parse(upload, data)
                if self._ingestion.claim_failed(existing.id):
                    existing = self._ingestion.ingest(existing.id, drafts)
            return UploadResult(existing, duplicate=True)

        drafts = self._parse(upload, data)

        key = self._storage.save(data, upload.extension)
        try:
            with self._session_factory.begin() as session:
                document = DocumentRepository(session).add(
                    Document(
                        name=upload.name,
                        sha256=sha256,
                        media_type=upload.media_type,
                        storage_key=key,
                        status="processing",
                    )
                )
        except IntegrityError:
            # Lost a race with a concurrent identical upload.
            self._storage.delete(key)
            existing = self._find_by_sha256(sha256)
            if existing is None:
                raise
            return UploadResult(existing, duplicate=True)
        except BaseException:
            self._storage.delete(key)
            raise
        return UploadResult(self._ingestion.ingest(document.id, drafts), duplicate=False)

    def list_documents(self) -> list[Document]:
        with self._session_factory() as session:
            return DocumentRepository(session).list_all()

    def get(self, document_id: uuid.UUID) -> Document:
        with self._session_factory() as session:
            document = DocumentRepository(session).get(document_id)
        if document is None:
            raise DocumentNotFoundError(str(document_id))
        return document

    def get_chunk(self, document_id: uuid.UUID, chunk_id: uuid.UUID) -> Chunk:
        with self._session_factory() as session:
            chunk = DocumentRepository(session).get_chunk(document_id, chunk_id)
        if chunk is None:
            raise ChunkNotFoundError(str(chunk_id))
        return chunk

    def file_path(self, document: Document) -> Path:
        path = self._storage.path_for(document.storage_key)
        if not path.is_file():
            raise DocumentNotFoundError(str(document.id))
        return path

    def _parse(self, upload: ValidatedUpload, data: bytes) -> list[ChunkDraft]:
        is_pdf = upload.media_type == PDF_MEDIA_TYPE
        pages = self._read_pdf_pages(data) if is_pdf else [PageText(None, data.decode("utf-8-sig"))]
        check_extractable_text([page.text for page in pages], is_pdf=is_pdf)
        return chunk_pages(pages)

    def _find_by_sha256(self, sha256: str) -> Document | None:
        with self._session_factory() as session:
            return DocumentRepository(session).get_by_sha256(sha256)
