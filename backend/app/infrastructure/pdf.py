"""PDF inspection with PyMuPDF."""

import pymupdf

from app.domain.documents import DocumentValidationError


def count_pdf_pages(data: bytes) -> int:
    """Return the page count; reject unreadable or password-protected PDFs."""
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            if document.needs_pass:
                raise DocumentValidationError(
                    "encrypted_pdf",
                    "The PDF is password-protected. Remove the password and upload again.",
                )
            return document.page_count
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise DocumentValidationError(
            "invalid_pdf", "The PDF could not be read; it may be corrupted."
        ) from exc
