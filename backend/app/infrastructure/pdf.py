"""PDF reading with PyMuPDF."""

import pymupdf

from app.domain.chunking import PageText
from app.domain.documents import DocumentValidationError, check_page_count


def read_pdf_pages(data: bytes) -> list[PageText]:
    """Extract text per page (1-based); reject unreadable, locked or oversized PDFs."""
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            if document.needs_pass:
                raise DocumentValidationError(
                    "encrypted_pdf",
                    "The PDF is password-protected. Remove the password and upload again.",
                )
            check_page_count(document.page_count)
            return [
                PageText(page=index + 1, text=page.get_text("text", sort=True).replace("\x00", ""))
                for index, page in enumerate(document)
            ]
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise DocumentValidationError(
            "invalid_pdf", "The PDF could not be read; it may be corrupted."
        ) from exc
