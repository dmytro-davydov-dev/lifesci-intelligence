"""Generate synthetic PDFs for tests."""

import pymupdf


def make_pdf(
    pages: list[str] | None = None, *, password: str | None = None, owner_only: bool = False
) -> bytes:
    document = pymupdf.open()
    for text in pages if pages is not None else ["Synthetic SOP page 1"]:
        document.new_page().insert_text((72, 72), text)
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
