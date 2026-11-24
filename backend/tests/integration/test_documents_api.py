import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.domain.documents import MAX_PDF_PAGES
from tests.support.pdfs import make_pdf

pytestmark = pytest.mark.integration


def upload(client: TestClient, name: str, data: bytes, content_type: str = "application/pdf"):
    return client.post("/api/documents", files={"file": (name, data, content_type)})


def test_upload_pdf_creates_processing_document_and_stores_file(
    client: TestClient, storage_dir: Path
) -> None:
    pdf = make_pdf(["Deviation SOP", "CAPA section"])
    response = upload(client, "deviation-sop.pdf", pdf)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "deviation-sop.pdf"
    assert body["media_type"] == "application/pdf"
    assert body["status"] == "processing"
    assert body["duplicate"] is False
    assert "storage_key" not in body
    assert [p.read_bytes() for p in storage_dir.iterdir()] == [pdf]


def test_upload_text_and_fetch_original_file(client: TestClient) -> None:
    created = upload(client, "notes.txt", b"Report deviations within 24 hours.", "text/plain")
    document_id = created.json()["id"]

    response = client.get(f"/api/documents/{document_id}/file")
    assert response.status_code == 200
    assert response.content == b"Report deviations within 24 hours."
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["content-disposition"].startswith("inline")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_duplicate_upload_returns_existing_document(client: TestClient, storage_dir: Path) -> None:
    pdf = make_pdf(["same content"])
    first = upload(client, "a.pdf", pdf).json()
    second = upload(client, "renamed.pdf", pdf)

    assert second.status_code == 200
    assert second.json()["id"] == first["id"]
    assert second.json()["name"] == "a.pdf"
    assert second.json()["duplicate"] is True
    assert len(list(storage_dir.iterdir())) == 1


def test_list_and_get_documents(client: TestClient) -> None:
    first = upload(client, "one.txt", b"one", "text/plain").json()
    second = upload(client, "two.txt", b"two", "text/plain").json()

    listed = client.get("/api/documents").json()
    assert {d["id"] for d in listed} == {first["id"], second["id"]}
    assert client.get(f"/api/documents/{first['id']}").json()["name"] == "one.txt"


def test_unknown_document_returns_404_envelope(client: TestClient) -> None:
    for path in (f"/api/documents/{uuid.uuid4()}", f"/api/documents/{uuid.uuid4()}/file"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "document_not_found"
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    ("name", "data", "status", "code"),
    [
        ("locked.pdf", make_pdf(password="pw"), 422, "encrypted_pdf"),
        ("huge.pdf", make_pdf(["p"] * (MAX_PDF_PAGES + 1)), 422, "too_many_pages"),
        ("fake.pdf", b"not a pdf", 422, "signature_mismatch"),
        ("script.html", b"<script>", 422, "unsupported_type"),
        ("empty.txt", b"", 422, "empty_file"),
    ],
)
def test_invalid_uploads_are_rejected_without_side_effects(
    client: TestClient, storage_dir: Path, name: str, data: bytes, status: int, code: str
) -> None:
    response = upload(client, name, data)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert client.get("/api/documents").json() == []
    assert not storage_dir.exists() or list(storage_dir.iterdir()) == []


def test_missing_file_field_is_validation_error(client: TestClient) -> None:
    response = client.post("/api/documents", data={"other": "x"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_database_failure_removes_stored_file(client: TestClient, storage_dir: Path) -> None:
    client = TestClient(client.app, raise_server_exceptions=False)
    with patch(
        "app.infrastructure.document_repository.DocumentRepository.add",
        side_effect=OperationalError("INSERT", {}, Exception("db down")),
    ):
        response = upload(client, "a.txt", b"content", "text/plain")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert list(storage_dir.iterdir()) == []


def test_missing_stored_file_returns_404(client: TestClient, storage_dir: Path) -> None:
    document_id = upload(client, "a.txt", b"content", "text/plain").json()["id"]
    for stored in storage_dir.iterdir():
        stored.unlink()

    response = client.get(f"/api/documents/{document_id}/file")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "file_not_found"


def test_pdf_file_response_is_viewable_inline(client: TestClient) -> None:
    document_id = upload(client, "guide.pdf", make_pdf(["guide"])).json()["id"]
    response = client.get(f"/api/documents/{document_id}/file")

    assert response.headers["content-type"] == "application/pdf"
    assert "content-security-policy" not in response.headers


def test_text_file_response_is_sandboxed(client: TestClient) -> None:
    document_id = upload(client, "x.md", b"<script>alert(1)</script>", "text/html").json()["id"]
    response = client.get(f"/api/documents/{document_id}/file")

    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.headers["content-security-policy"] == "sandbox"


def test_hostile_filename_is_sanitized_and_safely_quoted(
    client: TestClient, storage_dir: Path
) -> None:
    created = upload(client, "..\\..\\evil\u202e n\u00e4me.txt", b"content", "text/plain").json()

    assert created["name"] == "evil n\u00e4me.txt"
    [stored] = list(storage_dir.iterdir())
    assert stored.name.endswith(".txt") and len(stored.stem) == 32
    disposition = client.get(f"/api/documents/{created['id']}/file").headers["content-disposition"]
    assert disposition.startswith("inline")
    assert "filename*=utf-8''evil%20n%C3%A4me.txt" in disposition


def test_corrupt_pdf_is_rejected(client: TestClient) -> None:
    response = upload(client, "broken.pdf", b"%PDF-1.7 garbage")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_pdf"


def test_oversized_upload_without_content_length_hint_is_rejected(client: TestClient) -> None:
    with (
        patch("app.api.documents.MAX_UPLOAD_BYTES", 10),
        patch("app.domain.documents.MAX_UPLOAD_BYTES", 10),
    ):
        response = upload(client, "big.txt", b"a" * 50, "text/plain")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_lost_duplicate_race_returns_existing_document(
    client: TestClient, storage_dir: Path
) -> None:
    data = b"race content"
    first = upload(client, "first.txt", data, "text/plain").json()

    service = client.app.state.document_service
    real_find = service._find_by_sha256
    calls = {"n": 0}

    def find_misses_once(sha256: str):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_find(sha256)

    with patch.object(service, "_find_by_sha256", side_effect=find_misses_once):
        response = upload(client, "second.txt", data, "text/plain")

    assert response.status_code == 200
    assert response.json()["id"] == first["id"]
    assert response.json()["duplicate"] is True
    assert len(list(storage_dir.iterdir())) == 1
    assert len(client.get("/api/documents").json()) == 1
