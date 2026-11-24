"""Generate synthetic PDFs for tests."""

import pymupdf


def make_pdf(
    pages: list[str] | None = None, *, password: str | None = None, owner_only: bool = False
) -> bytes:
    document = pymupdf.open()
    for text in pages if pages is not None else ["Synthetic SOP page 1"]:
        page = document.new_page()
        # Wrapped text box so long text stays on the page and remains extractable.
        page.insert_textbox(page.rect + (72, 72, -72, -72), text, fontsize=10)
    if password:
        data = document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw=password,
            user_pw="" if owner_only else password,
        )
    else:
        data = document.tobytes()
    document.close()
    return data
