import uuid

import pytest
from sqlalchemy.orm import Session

from app.infrastructure.fake_providers import FakeEmbeddingProvider
from app.infrastructure.models import Document
from app.infrastructure.retrieval import hybrid_search, keyword_search, vector_search
from tests.support.pdfs import make_pdf

pytestmark = pytest.mark.integration

SOP = [
    "4.2 Deviation Reporting\nOperators report every deviation to Quality Assurance within "
    "24 hours using form QA-12.",
]
CALIBRATION = ["2. Calibration\nBalances are calibrated every twelve months by metrology staff."]


def upload(client, pages, name) -> str:
    response = client.post(
        "/api/documents", files={"file": (name, make_pdf(pages), "application/pdf")}
    )
    assert response.json()["status"] == "ready"
    return response.json()["id"]


@pytest.fixture
def corpus(make_client):
    client = make_client()
    return upload(client, SOP, "sop.pdf"), upload(client, CALIBRATION, "cal.pdf")


def test_keyword_search_matches_terms_and_ranks_best_first(engine, corpus) -> None:
    sop_id, _ = corpus
    with Session(engine) as session:
        results = keyword_search(session, "Which form is QA-12?", None, 5)
    assert [str(r.document_id) for r in results] == [sop_id]
    assert results[0].score > 0


def test_keyword_search_respects_scope_and_ignores_stopword_only_queries(engine, corpus) -> None:
    _, cal_id = corpus
    with Session(engine) as session:
        scoped = keyword_search(session, "form QA-12 balances", [uuid.UUID(cal_id)], 5)
        empty = keyword_search(session, "what is the", None, 5)
        punctuation = keyword_search(session, "?!", None, 5)
    assert [str(r.document_id) for r in scoped] == [cal_id]
    assert empty == [] and punctuation == []


def test_keyword_search_excludes_documents_that_are_not_ready(engine, corpus) -> None:
    sop_id, _ = corpus
    with Session(engine) as session:
        session.get(Document, uuid.UUID(sop_id)).status = "failed"
        session.commit()
        assert keyword_search(session, "deviation QA-12", None, 5) == []


def test_hybrid_unions_vector_and_keyword_candidates(engine, corpus) -> None:
    sop_id, cal_id = corpus
    # Separate inputs make each branch's top hit a different document.
    vector = FakeEmbeddingProvider().embed(["calibrated balances metrology staff"])[0]
    with Session(engine) as session:
        vector_only = vector_search(session, vector, None, 1)
        keyword_only = keyword_search(session, "form QA-12", None, 1)
        fused = hybrid_search(session, vector, "form QA-12", None, 2, candidate_pool=1)
    assert [str(r.document_id) for r in vector_only] == [cal_id]
    assert [str(r.document_id) for r in keyword_only] == [sop_id]
    assert {str(r.document_id) for r in fused} == {sop_id, cal_id}
    assert all(r.score == pytest.approx(1 / 61) for r in fused)


def test_hybrid_scope_applies_to_both_branches(engine, corpus) -> None:
    sop_id, _ = corpus
    vector = FakeEmbeddingProvider().embed(["calibrated balances metrology staff"])[0]
    with Session(engine) as session:
        fused = hybrid_search(session, vector, "balances QA-12", [uuid.UUID(sop_id)], 8)
    assert {str(r.document_id) for r in fused} == {sop_id}


@pytest.mark.parametrize("mode", ["vector", "hybrid"])
def test_chat_answers_in_both_retrieval_modes(make_client, mode: str) -> None:
    client = make_client(settings_overrides={"retrieval_mode": mode})
    upload(client, SOP, "sop.pdf")
    body = client.post(
        "/api/chat", json={"question": "Which form is used to report a deviation?"}
    ).json()
    assert body["status"] == "answered"
    assert body["citations"][0]["document_name"] == "sop.pdf"


@pytest.mark.parametrize("question", ["24", "x" * 2000, "über Säure 2.5 µg"])
def test_unusual_terms_never_raise(engine, corpus, question: str) -> None:
    with Session(engine) as session:
        keyword_search(session, question, None, 5)


def test_numeric_query_matches_numbers_in_text(engine, corpus) -> None:
    sop_id, _ = corpus
    with Session(engine) as session:
        results = keyword_search(session, "24", None, 5)
    assert [str(r.document_id) for r in results] == [sop_id]
