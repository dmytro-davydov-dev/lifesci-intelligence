import pytest

from app.domain.documents import MAX_PDF_PAGES, DocumentValidationError
from app.infrastructure.pdf import read_pdf_pages
from tests.support.pdfs import make_pdf


def test_extracts_text_per_page_with_one_based_numbers() -> None:
    pages = read_pdf_pages(make_pdf(["First page", "Second page"]))
    assert [(p.page, p.text.strip()) for p in pages] == [(1, "First page"), (2, "Second page")]


def test_owner_password_only_pdf_is_accepted() -> None:
    assert len(read_pdf_pages(make_pdf(["restricted"], password="owner", owner_only=True))) == 1


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (make_pdf(password="secret"), "encrypted_pdf"),
        (b"%PDF-1.7 truncated garbage", "invalid_pdf"),
        (make_pdf(["p"] * (MAX_PDF_PAGES + 1)), "too_many_pages"),
    ],
)
def test_rejects_unreadable_pdfs(data: bytes, code: str) -> None:
    with pytest.raises(DocumentValidationError) as info:
        read_pdf_pages(data)
    assert info.value.code == code
