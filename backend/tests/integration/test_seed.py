import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.corpus import load_golden_dataset
from app.infrastructure.models import Chunk, Document
from app.seed import seed_corpus
from tests.support.corpus import CORPUS_DIR

pytestmark = pytest.mark.integration


def test_seed_ingests_sample_documents_idempotently(client: TestClient, engine: Engine) -> None:
    service = client.app.state.document_service

    first = seed_corpus(service, CORPUS_DIR)
    second = seed_corpus(service, CORPUS_DIR)

    assert [o.outcome for o in first] == ["created"] * 7
    assert all(o.status == "ready" for o in first)
    assert [o.outcome for o in second] == ["duplicate"] * 7
    with Session(engine) as session:
        documents = {d.name: d for d in session.scalars(select(Document))}
    assert len(documents) == 7
    assert documents["SOP-001-v2.pdf"].version == "2.0"
    assert documents["OPS-NOTE-001.txt"].version is None
    assert not any("INJECTION" in name for name in documents)


def test_seeded_knowledge_base_contains_no_evaluation_questions(
    client: TestClient, engine: Engine
) -> None:
    seed_corpus(client.app.state.document_service, CORPUS_DIR)
    with Session(engine) as session:
        corpus_text = " ".join(session.scalars(select(Chunk.text))).lower()

    for case in load_golden_dataset(CORPUS_DIR):
        assert case.question.lower() not in corpus_text, case.id
    assert "expected_status" not in corpus_text
    assert "blue orchid override" not in corpus_text


def test_seeded_corpus_answers_a_golden_question_with_correct_evidence(client: TestClient) -> None:
    seed_corpus(client.app.state.document_service, CORPUS_DIR)
    sop = next(d for d in client.get("/api/documents").json() if d["name"] == "SOP-001-v2.pdf")

    body = client.post(
        "/api/chat",
        json={
            "question": "How soon must a deviation be recorded under the current SOP-001?",
            "document_ids": [sop["id"]],
        },
    ).json()

    # Document-level grounding only: page-level accuracy depends on the (lexical, offline)
    # providers and is measured by the evaluation harness, not asserted here.
    assert body["status"] == "answered"
    assert {c["document_name"] for c in body["citations"]} == {"SOP-001-v2.pdf"}
