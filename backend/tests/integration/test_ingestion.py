import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.domain.providers import EmbeddingError
from app.infrastructure.fake_providers import FakeEmbeddingProvider
from app.infrastructure.models import Chunk
from tests.support.pdfs import make_pdf

pytestmark = pytest.mark.integration

SOP_PAGES = [
    "1. Purpose\nThis synthetic SOP defines deviation handling for the packaging line.",
    "4.2 Deviation Reporting\nOperators report deviations to QA within 24 hours.",
]


class FailingEmbedder(FakeEmbeddingProvider):
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("Embedding request failed (APITimeoutError). Retry the upload later.")


class WrongDimensionEmbedder(FakeEmbeddingProvider):
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 3 for _ in texts]


def upload_pdf(client, data: bytes, name: str = "sop.pdf"):
    return client.post("/api/documents", files={"file": (name, data, "application/pdf")})


def chunks_of(engine: Engine, document_id: str) -> list[Chunk]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(Chunk)
                .where(Chunk.document_id == uuid.UUID(document_id))
                .order_by(Chunk.ordinal)
            )
        )


def test_pdf_ingestion_persists_page_aware_chunks(make_client, engine: Engine) -> None:
    response = upload_pdf(make_client(), make_pdf(SOP_PAGES))
    body = response.json()

    assert (response.status_code, body["status"]) == (201, "ready")
    chunks = chunks_of(engine, body["id"])
    assert [(c.ordinal, c.page) for c in chunks] == [(0, 1), (1, 2)]
    assert chunks[1].section == "4.2 Deviation Reporting"
    assert "within 24 hours" in chunks[1].text
    assert len(chunks[0].embedding) == 1536


def test_text_ingestion_has_no_page_numbers(make_client, engine: Engine) -> None:
    body = (
        make_client()
        .post("/api/documents", files={"file": ("n.md", b"# CAPA\nOwners close CAPAs.", "x")})
        .json()
    )
    assert body["status"] == "ready"
    assert [(c.page, c.section) for c in chunks_of(engine, body["id"])] == [(None, "CAPA")]


@pytest.mark.parametrize(
    ("embedder", "message"),
    [
        (FailingEmbedder(), "APITimeoutError"),
        (WrongDimensionEmbedder(), "unexpected result"),
    ],
)
def test_embedding_failure_marks_document_failed_without_chunks(
    make_client, engine: Engine, embedder, message: str
) -> None:
    response = upload_pdf(make_client(embedder), make_pdf(SOP_PAGES))
    body = response.json()

    assert response.status_code == 201
    assert body["status"] == "failed"
    assert message in body["error"]
    assert chunks_of(engine, body["id"]) == []


def test_persistence_failure_rolls_back_partial_chunks(make_client, engine: Engine) -> None:
    from app.infrastructure.document_repository import DocumentRepository

    real_replace = DocumentRepository.replace_chunks

    def replace_then_fail(self, *args, **kwargs):
        real_replace(self, *args, **kwargs)  # chunks flushed inside the transaction
        raise RuntimeError("disk full")

    with patch.object(DocumentRepository, "replace_chunks", replace_then_fail):
        body = upload_pdf(make_client(), make_pdf(SOP_PAGES)).json()

    assert body["status"] == "failed"
    assert body["error"] == "Ingestion failed (RuntimeError). Retry the upload."
    assert chunks_of(engine, body["id"]) == []


def test_reuploading_failed_document_retries_ingestion(
    make_client, engine: Engine, storage_dir: Path
) -> None:
    data = make_pdf(SOP_PAGES)
    failed = upload_pdf(make_client(FailingEmbedder()), data).json()
    retried = upload_pdf(make_client(), data, name="retry.pdf")

    assert retried.status_code == 200
    assert retried.json()["id"] == failed["id"]
    assert retried.json()["duplicate"] is True
    assert retried.json()["status"] == "ready"
    assert len(chunks_of(engine, failed["id"])) == 2
    assert len(list(storage_dir.iterdir())) == 1


def test_reuploading_ready_document_does_not_reingest(make_client) -> None:
    data = make_pdf(SOP_PAGES)
    first = upload_pdf(make_client(), data).json()
    again = upload_pdf(make_client(FailingEmbedder()), data).json()

    assert again["status"] == "ready"
    assert again["id"] == first["id"]


@pytest.mark.parametrize("pages", [["", ""], ["1", "2"]])
def test_scanned_pdf_is_rejected_before_storage(
    client, storage_dir: Path, pages: list[str]
) -> None:
    response = upload_pdf(client, make_pdf(pages))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_extractable_text"
    assert client.get("/api/documents").json() == []
    assert not storage_dir.exists() or list(storage_dir.iterdir()) == []


def test_long_pdf_pages_split_into_multiple_chunks_per_page(make_client, engine: Engine) -> None:
    sentence = "Synthetic SOP text about deviation handling and CAPA review. "
    pages = [f"{n}. Section {n}\n" + sentence * 60 for n in (1, 2)]
    body = upload_pdf(make_client(), make_pdf(pages)).json()

    chunks = chunks_of(engine, body["id"])
    assert body["status"] == "ready"
    assert {c.page for c in chunks} == {1, 2}
    assert sum(c.page == 1 for c in chunks) >= 2
    assert all(len(c.text) <= 2000 for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_utf8_bom_is_stripped_from_text_files(make_client, engine: Engine) -> None:
    data = "﻿# Scope\nApplies to line 3.".encode()
    body = make_client().post("/api/documents", files={"file": ("bom.md", data, "x")}).json()
    [chunk] = chunks_of(engine, body["id"])
    assert chunk.section == "Scope"
    assert not chunk.text.startswith("﻿")


def test_chunks_stay_ordered_across_embedding_batches(
    database_url: str, clean_db: None, storage_dir: Path, engine: Engine
) -> None:
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    settings = Settings(database_url=database_url, storage_dir=storage_dir, embedding_batch_size=1)
    pages = [f"Page {n} content about deviation handling procedures." for n in range(1, 5)]
    with TestClient(create_app(settings)) as client:
        body = upload_pdf(client, make_pdf(pages)).json()

    chunks = chunks_of(engine, body["id"])
    embedder = FakeEmbeddingProvider()
    assert [c.page for c in chunks] == [1, 2, 3, 4]
    for chunk in chunks:
        assert list(chunk.embedding) == pytest.approx(embedder.embed([chunk.text])[0])
