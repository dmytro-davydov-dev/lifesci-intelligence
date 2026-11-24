import pytest

from app.domain.documents import (
    MAX_NAME_LENGTH,
    MAX_PDF_PAGES,
    MAX_UPLOAD_BYTES,
    DocumentValidationError,
    check_page_count,
    sanitize_filename,
    validate_upload,
)


def error_code(name: str | None, data: bytes) -> str:
    with pytest.raises(DocumentValidationError) as info:
        validate_upload(name, data)
    return info.value.code


@pytest.mark.parametrize(
    ("name", "media_type", "extension"),
    [
        ("sop.txt", "text/plain", ".txt"),
        ("Notes.MD", "text/markdown", ".md"),
    ],
)
def test_accepts_utf8_text(name: str, media_type: str, extension: str) -> None:
    result = validate_upload(name, "Déviation: report within 24 h".encode())
    assert (result.media_type, result.extension) == (media_type, extension)


def test_accepts_pdf_signature() -> None:
    assert validate_upload("guide.pdf", b"%PDF-1.7 ...").media_type == "application/pdf"


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("malware.exe", b"MZ", "unsupported_type"),
        ("noext", b"text", "unsupported_type"),
        ("empty.txt", b"", "empty_file"),
        ("fake.pdf", b"hello", "signature_mismatch"),
        ("disguised.txt", b"%PDF-1.7", "signature_mismatch"),
        ("binary.txt", b"abc\x00def", "invalid_text"),
        ("latin1.txt", "café".encode("latin-1"), "invalid_text"),
        (None, b"x", "invalid_filename"),
        ("../", b"x", "invalid_filename"),
    ],
)
def test_rejects_invalid_uploads(name: str | None, data: bytes, code: str) -> None:
    assert error_code(name, data) == code


def test_rejects_oversized_file() -> None:
    assert error_code("big.txt", b"a" * (MAX_UPLOAD_BYTES + 1)) == "file_too_large"


def test_accepts_file_at_size_limit() -> None:
    validate_upload("max.txt", b"a" * MAX_UPLOAD_BYTES)


def test_sanitize_strips_paths_and_control_characters() -> None:
    assert sanitize_filename("../../etc/pass\x00wd.txt") == "passwd.txt"
    assert sanitize_filename("C:\\Users\\me\\SOP 12.pdf") == "SOP 12.pdf"


def test_sanitize_truncates_long_names_keeping_extension() -> None:
    name = sanitize_filename("a" * 400 + ".pdf")
    assert len(name) == MAX_NAME_LENGTH
    assert name.endswith(".pdf")


@pytest.mark.parametrize(
    ("pages", "code"), [(0, "invalid_pdf"), (MAX_PDF_PAGES + 1, "too_many_pages")]
)
def test_page_count_limits(pages: int, code: str) -> None:
    with pytest.raises(DocumentValidationError) as info:
        check_page_count(pages)
    assert info.value.code == code


def test_page_count_at_limit_is_allowed() -> None:
    check_page_count(MAX_PDF_PAGES)
