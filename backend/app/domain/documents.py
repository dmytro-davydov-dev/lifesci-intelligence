"""Upload validation policy. Pure functions; no framework or I/O."""

import re
import unicodedata
from dataclasses import dataclass

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_NAME_LENGTH = 255

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
}
PDF_MEDIA_TYPE = MEDIA_TYPES[".pdf"]


class DocumentValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValidatedUpload:
    name: str
    extension: str
    media_type: str


def sanitize_filename(raw: str | None) -> str:
    """Keep only the base name, drop control characters and cap the length."""
    base = re.split(r"[\\/]", raw or "")[-1]
    cleaned = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C").strip()
    if not cleaned or cleaned in {".", ".."}:
        raise DocumentValidationError("invalid_filename", "File name is missing or invalid.")
    if len(cleaned) > MAX_NAME_LENGTH:
        stem, dot, ext = cleaned.rpartition(".")
        suffix = f".{ext}" if dot and len(ext) <= 10 else ""
        cleaned = (stem if suffix else cleaned)[: MAX_NAME_LENGTH - len(suffix)] + suffix
    return cleaned


def validate_upload(raw_name: str | None, data: bytes) -> ValidatedUpload:
    name = sanitize_filename(raw_name)
    extension = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    media_type = MEDIA_TYPES.get(extension)
    if media_type is None:
        allowed = ", ".join(sorted(MEDIA_TYPES))
        raise DocumentValidationError(
            "unsupported_type", f"Unsupported file type. Allowed extensions: {allowed}."
        )
    if not data:
        raise DocumentValidationError("empty_file", "The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise DocumentValidationError(
            "file_too_large", f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
        )
    if media_type == PDF_MEDIA_TYPE:
        if not data.startswith(b"%PDF-"):
            raise DocumentValidationError(
                "signature_mismatch", "File has a .pdf extension but is not a PDF."
            )
    else:
        _validate_text(data)
    return ValidatedUpload(name=name, extension=extension, media_type=media_type)


def check_page_count(page_count: int) -> None:
    if page_count < 1:
        raise DocumentValidationError("invalid_pdf", "The PDF has no pages.")
    if page_count > MAX_PDF_PAGES:
        raise DocumentValidationError(
            "too_many_pages", f"PDF has {page_count} pages; the limit is {MAX_PDF_PAGES}."
        )


def _validate_text(data: bytes) -> None:
    if data.startswith(b"%PDF-"):
        raise DocumentValidationError(
            "signature_mismatch", "File content is a PDF; upload it with a .pdf extension."
        )
    if b"\x00" in data:
        raise DocumentValidationError("invalid_text", "Text file contains binary data.")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentValidationError("invalid_text", "Text files must be UTF-8 encoded.") from exc
