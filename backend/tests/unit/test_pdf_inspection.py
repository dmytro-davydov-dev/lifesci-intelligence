import pytest

from app.domain.documents import DocumentValidationError
from app.infrastructure.pdf import count_pdf_pages
from tests.support.pdfs import make_pdf


def test_owner_password_only_pdf_is_accepted() -> None:
    assert count_pdf_pages(make_pdf(["restricted"], password="owner", owner_only=True)) == 1


def test_counts_pages() -> None:
    assert count_pdf_pages(make_pdf(["one", "two", "three"])) == 3


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (make_pdf(password="secret"), "encrypted_pdf"),
        (b"%PDF-1.7 truncated garbage", "invalid_pdf"),
    ],
)
def test_rejects_unreadable_pdfs(data: bytes, code: str) -> None:
    with pytest.raises(DocumentValidationError) as info:
        count_pdf_pages(data)
    assert info.value.code == code
