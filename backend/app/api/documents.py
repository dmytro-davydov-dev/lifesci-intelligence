"""Document upload, listing and original-file routes."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from app.api.errors import ApiError
from app.application.documents import DocumentNotFoundError, DocumentService
from app.domain.documents import MAX_UPLOAD_BYTES, DocumentValidationError

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    media_type: str
    sha256: str
    version: str | None
    status: str
    error: str | None
    created_at: datetime


class UploadOut(DocumentOut):
    duplicate: bool


def get_document_service(request: Request) -> DocumentService:
    return request.app.state.document_service


Service = Annotated[DocumentService, Depends(get_document_service)]


@router.post("", status_code=201, response_model=UploadOut)
def upload_document(file: Annotated[UploadFile, File()], response: Response, service: Service):
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    try:
        result = service.upload(file.filename, data)
    except DocumentValidationError as exc:
        status = 413 if exc.code == "file_too_large" else 422
        raise ApiError(status, exc.code, exc.message) from exc
    if result.duplicate:
        response.status_code = 200
    return UploadOut(
        **DocumentOut.model_validate(result.document).model_dump(), duplicate=result.duplicate
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(service: Service):
    return service.list_documents()


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, service: Service):
    return _get_or_404(service, document_id)


@router.get("/{document_id}/file")
def get_document_file(document_id: uuid.UUID, service: Service) -> FileResponse:
    document = _get_or_404(service, document_id)
    try:
        path = service.file_path(document)
    except DocumentNotFoundError as exc:
        raise ApiError(404, "file_not_found", "The original file is not available.") from exc
    media_type = document.media_type
    headers = {"X-Content-Type-Options": "nosniff"}
    if media_type.startswith("text/"):
        media_type += "; charset=utf-8"
        # Sandbox text so it can never run script in the API origin. Not applied to PDFs:
        # a sandboxed document cannot load the browser's built-in PDF viewer.
        headers["Content-Security-Policy"] = "sandbox"
    return FileResponse(
        path,
        media_type=media_type,
        filename=document.name,
        content_disposition_type="inline",
        headers=headers,
    )


def _get_or_404(service: DocumentService, document_id: uuid.UUID):
    try:
        return service.get(document_id)
    except DocumentNotFoundError as exc:
        raise ApiError(404, "document_not_found", "Document not found.") from exc
