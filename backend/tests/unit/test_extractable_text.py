import pytest

from app.domain.documents import DocumentValidationError, check_extractable_text


@pytest.mark.parametrize(
    ("texts", "is_pdf"),
    [
        (["", " \n"], True),  # blank scanned pages
        (["1", "2", "3"], True),  # page numbers only
        (["   "], False),
    ],
)
def test_rejects_documents_without_text(texts: list[str], is_pdf: bool) -> None:
    with pytest.raises(DocumentValidationError) as info:
        check_extractable_text(texts, is_pdf=is_pdf)
    assert info.value.code == "no_extractable_text"


@pytest.mark.parametrize(
    ("texts", "is_pdf"),
    [
        (["Deviation handling SOP"], True),
        (["ok"], False),
        (["", "This page carries enough text."], True),
    ],
)
def test_accepts_documents_with_text(texts: list[str], is_pdf: bool) -> None:
    check_extractable_text(texts, is_pdf=is_pdf)
