import json
import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.domain.providers import ChatError
from app.infrastructure.fake_providers import ScriptedChatProvider
from app.infrastructure.models import Chunk, Message
from tests.support.pdfs import make_pdf

pytestmark = pytest.mark.integration

SOP = [
    "1. Purpose\nThis synthetic SOP covers deviation handling on the packaging line.",
    "4.2 Deviation Reporting\nOperators report every deviation to Quality Assurance within "
    "24 hours of discovery using form QA-12.",
]
CALIBRATION = ["2. Calibration\nBalances are calibrated every twelve months by metrology staff."]


def reply(status="answered", answer="Within 24 hours [S1].", ids=("S1",)) -> str:
    return json.dumps({"status": status, "answer": answer, "citation_ids": list(ids)})


def upload(client, pages, name="sop.pdf") -> dict:
    response = client.post(
        "/api/documents", files={"file": (name, make_pdf(pages), "application/pdf")}
    )
    assert response.json()["status"] == "ready"
    return response.json()


def ask(client, question: str, **extra):
    return client.post("/api/chat", json={"question": question, **extra})


def test_answers_with_citation_derived_from_database(make_client, engine: Engine) -> None:
    client = make_client()
    document = upload(client, SOP)

    response = ask(
        client, "Within how many hours must a deviation be reported to Quality Assurance?"
    )
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "answered"
    [citation] = body["citations"]
    assert citation["label"] == "S1"
    assert citation["document_id"] == document["id"]
    assert citation["document_name"] == "sop.pdf"
    assert citation["page"] == 2
    assert citation["section"] == "4.2 Deviation Reporting"
    with Session(engine) as session:
        stored = session.get(Chunk, uuid.UUID(citation["chunk_id"]))
    assert stored.text.startswith(citation["quote"].removesuffix("..."))
    assert "[S1]" in body["answer"]


def test_unrelated_question_abstains(make_client) -> None:
    client = make_client()
    upload(client, SOP)
    body = ask(client, "What is the capital of France?").json()
    assert (body["status"], body["citations"]) == ("insufficient_evidence", [])


def test_no_ready_documents_abstains_without_calling_model(make_client) -> None:
    chat = ScriptedChatProvider([])  # any call would raise IndexError
    body = ask(make_client(chat_provider=chat), "When are deviations reported?").json()

    assert body["status"] == "insufficient_evidence"
    assert chat.calls == []


def test_invalid_citation_is_repaired_once(make_client) -> None:
    chat = ScriptedChatProvider([reply(ids=["S99"]), reply()])
    client = make_client(chat_provider=chat)
    upload(client, SOP)

    body = ask(client, "When are deviations reported?").json()

    assert body["status"] == "answered"
    assert len(chat.calls) == 2
    assert "Unknown citation ids: S99" in chat.calls[1][-1].content


@pytest.mark.parametrize(
    "bad",
    [reply(ids=["S99"]), reply(answer="Uncited claim.", ids=[]), "not json"],
)
def test_abstains_after_failed_repair(make_client, bad: str) -> None:
    chat = ScriptedChatProvider([bad, bad])
    client = make_client(chat_provider=chat)
    upload(client, SOP)

    body = ask(client, "When are deviations reported?").json()

    assert (body["status"], body["citations"]) == ("insufficient_evidence", [])
    assert len(chat.calls) == 2


def test_clarification_status_is_returned_without_citations(make_client) -> None:
    chat = ScriptedChatProvider([reply("clarification", "Which SOP do you mean?", ["S1"])])
    client = make_client(chat_provider=chat)
    upload(client, SOP)
    body = ask(client, "What is the deadline?").json()
    assert (body["status"], body["citations"]) == ("clarification", [])


def test_document_scope_restricts_retrieval(make_client) -> None:
    client = make_client()
    upload(client, SOP)
    calibration = upload(client, CALIBRATION, name="cal.pdf")

    body = ask(client, "When must deviations be reported?", document_ids=[calibration["id"]]).json()

    assert all(c["document_id"] == calibration["id"] for c in body["citations"])
    assert body["status"] == "insufficient_evidence"


@pytest.mark.parametrize("ids", [[], [str(uuid.uuid4())]])
def test_invalid_document_scope_is_rejected(make_client, ids: list[str]) -> None:
    response = ask(make_client(), "Question?", document_ids=ids)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_document_scope"


def test_failed_documents_are_excluded_from_scope_and_retrieval(
    make_client, engine: Engine
) -> None:
    client = make_client()
    document = upload(client, SOP)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE documents SET status = 'failed' WHERE id = :id"), {"id": document["id"]}
        )

    scoped = ask(client, "When are deviations reported?", document_ids=[document["id"]])
    unscoped = ask(client, "When are deviations reported?").json()

    assert scoped.status_code == 422
    assert unscoped["status"] == "insufficient_evidence"


def test_conversation_persists_and_history_is_sent_as_context(make_client, engine: Engine) -> None:
    chat = ScriptedChatProvider([reply(), reply(answer="Use form QA-12 [S1].")])
    client = make_client(chat_provider=chat)
    upload(client, SOP)

    first = ask(client, "When are deviations reported?").json()
    second = ask(client, "Which form is used?", conversation_id=first["conversation_id"]).json()

    assert second["conversation_id"] == first["conversation_id"]
    roles = [m.role for m in chat.calls[1]]
    assert roles == ["system", "user", "assistant", "user"]
    assert chat.calls[1][1].content == "When are deviations reported?"
    with Session(engine) as session:
        stored = (
            session.query(Message)
            .filter_by(conversation_id=uuid.UUID(first["conversation_id"]))
            .count()
        )
    assert stored == 4


def test_unknown_conversation_returns_404(make_client) -> None:
    response = ask(make_client(), "Hi there?", conversation_id=str(uuid.uuid4()))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "conversation_not_found"


def test_compare_mode_is_not_available_yet(make_client) -> None:
    response = ask(make_client(), "Compare SOP to Q10", mode="compare")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mode_unavailable"


def test_provider_failure_returns_503_and_persists_nothing(make_client, engine: Engine) -> None:
    class BrokenChat:
        def complete_json(self, *args):
            raise ChatError("Model request failed (APITimeoutError). Try again shortly.")

    client = make_client(chat_provider=BrokenChat())
    upload(client, SOP)
    response = ask(client, "When are deviations reported?")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_unavailable"
    with Session(engine) as session:
        assert session.query(Message).count() == 0


@pytest.mark.parametrize("question", ["   ", "x" * 2001])
def test_question_validation(make_client, question: str) -> None:
    response = ask(make_client(), question)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_chunk_endpoint_returns_source_passage_scoped_to_document(make_client) -> None:
    client = make_client()
    document = upload(client, SOP)
    other = upload(client, CALIBRATION, name="cal.pdf")
    citation = ask(client, "When must deviations be reported to Quality Assurance?").json()[
        "citations"
    ][0]

    passage = client.get(f"/api/documents/{document['id']}/chunks/{citation['chunk_id']}")
    wrong_document = client.get(f"/api/documents/{other['id']}/chunks/{citation['chunk_id']}")

    assert passage.status_code == 200
    assert passage.json()["page"] == 2
    assert "24 hours" in passage.json()["text"]
    assert wrong_document.status_code == 404
    assert wrong_document.json()["error"]["code"] == "chunk_not_found"


def test_history_markers_are_stripped_before_reuse(make_client) -> None:
    chat = ScriptedChatProvider([reply(answer="Within 24 hours [S1]."), reply()])
    client = make_client(chat_provider=chat)
    upload(client, SOP)

    first = ask(client, "When are deviations reported?").json()
    ask(client, "And which form?", conversation_id=first["conversation_id"])

    history_assistant = chat.calls[1][2]
    assert history_assistant.role == "assistant"
    assert "[S1]" not in history_assistant.content


def test_validation_failure_logs_reason_code_not_model_text(make_client, caplog) -> None:
    leaked = "Operators report every deviation to Quality Assurance"
    chat = ScriptedChatProvider([reply(ids=[leaked]), reply(ids=[leaked])])
    client = make_client(chat_provider=chat)
    upload(client, SOP)

    with caplog.at_level("WARNING", logger="app.chat"):
        body = ask(client, "When are deviations reported?").json()

    assert body["status"] == "insufficient_evidence"
    assert "code=unknown_citation" in caplog.text
    assert leaked not in caplog.text
    assert leaked not in chat.calls[1][-1].content


def test_provider_failure_on_repair_returns_503_and_persists_nothing(
    make_client, engine: Engine
) -> None:
    class FailsOnRepair:
        def __init__(self) -> None:
            self.calls = 0

        def complete_json(self, *args):
            self.calls += 1
            if self.calls == 1:
                return reply(ids=["S99"])
            raise ChatError("Model request failed (APITimeoutError). Try again shortly.")

    client = make_client(chat_provider=FailsOnRepair())
    upload(client, SOP)

    assert ask(client, "When are deviations reported?").status_code == 503
    with Session(engine) as session:
        assert session.query(Message).count() == 0
