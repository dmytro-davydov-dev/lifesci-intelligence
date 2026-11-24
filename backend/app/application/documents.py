"""Document upload and lookup use cases."""

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.domain.documents import PDF_MEDIA_TYPE, check_page_count, validate_upload
from app.infrastructure.document_repository import DocumentRepository
from app.infrastructure.models import Document
from app.infrastructure.storage import LocalFileStorage

PdfPageCounter = Callable[[bytes], int]


class DocumentNotFoundError(Exception):
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
        count_pdf_pages: PdfPageCounter,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._count_pdf_pages = count_pdf_pages

    def upload(self, filename: str | None, data: bytes) -> UploadResult:
        upload = validate_upload(filename, data)
        if upload.media_type == PDF_MEDIA_TYPE:
            check_page_count(self._count_pdf_pages(data))
        sha256 = hashlib.sha256(data).hexdigest()

        existing = self._find_by_sha256(sha256)
        if existing is not None:
            return UploadResult(existing, duplicate=True)

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
        return UploadResult(document, duplicate=False)

    def list(self) -> list[Document]:
        with self._session_factory() as session:
            return DocumentRepository(session).list()

    def get(self, document_id: uuid.UUID) -> Document:
        with self._session_factory() as session:
            document = DocumentRepository(session).get(document_id)
        if document is None:
            raise DocumentNotFoundError(str(document_id))
        return document

    def file_path(self, document: Document) -> Path:
        path = self._storage.path_for(document.storage_key)
        if not path.is_file():
            raise DocumentNotFoundError(str(document.id))
        return path

    def _find_by_sha256(self, sha256: str) -> Document | None:
        with self._session_factory() as session:
            return DocumentRepository(session).get_by_sha256(sha256)
