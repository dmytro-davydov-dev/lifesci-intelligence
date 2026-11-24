"""Comparison agent end to end: routing, model-selected read-only tools, scope and tracing."""

import json
import uuid

import pytest

from app.application.agent_prompts import AGENT_SYSTEM_PROMPT
from app.infrastructure.fake_providers import ScriptedChatProvider
from tests.support.pdfs import make_pdf
from tests.support.tracing import RecordingTracer

pytestmark = pytest.mark.integration

SOP = [
    "2. Deviation Reporting\nOperators record every deviation within 48 hours of discovery.",
    "5. Closure\nQA approves deviation closure.",
]
REFERENCE = ["2. Reporting\nDeviations shall be reported within 24 hours of discovery."]
CALIBRATION = ["1. Calibration\nBalances are calibrated every twelve months."]
QUESTION = "Compare deviation reporting deadlines in the SOP and the reference."


def step(action, query=None, document=None, source=None) -> str:
    return json.dumps({"action": action, "query": query, "document": document, "source": source})


def answer(text="48 hours [S1] versus 24 hours [S2].", ids=("S1", "S2")) -> str:
    return json.dumps({"status": "answered", "answer": text, "citation_ids": list(ids)})


def upload(client, pages, name) -> str:
    response = client.post(
        "/api/documents", files={"file": (name, make_pdf(pages), "application/pdf")}
    )
    assert response.json()["status"] == "ready"
    return response.json()["id"]


def corpus(client) -> dict[str, str]:
    # Labels follow document name order: D1 = qms-ref.pdf, D2 = sop-001.pdf.
    sop = upload(client, SOP, "sop-001.pdf")
    return {"sop": sop, "ref": upload(client, REFERENCE, "qms-ref.pdf")}


def ask(client, question=QUESTION, **extra):
    return client.post("/api/chat", json={"question": question, **extra})


def test_auto_routes_comparison_through_model_selected_tools(make_client) -> None:
    chat = ScriptedChatProvider(
        [
            step("list_documents"),
            step("search", "deviation reporting hours", "D2"),
            step("search", "deviation reporting hours", "D1"),
            step("finish"),
            answer(),
        ]
    )
    tracer = RecordingTracer()
    client = make_client(
        chat_provider=chat, tracer=tracer, settings_overrides={"agent_results_per_search": 1}
    )
    ids = corpus(client)

    response = ask(client)
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "answered"
    assert [c["document_id"] for c in body["citations"]] == [ids["sop"], ids["ref"]]
    assert body["citations"][0]["page"] == 1
    # Four planning calls with the agent prompt, then one grounded answer call.
    assert [m[0].content == AGENT_SYSTEM_PROMPT for m in chat.calls] == [True] * 4 + [False]
    final_planning_prompt = chat.calls[3][-1].content
    assert 'D1 name="qms-ref.pdf"' in final_planning_prompt
    assert "document=D2 -> S1 (new)" in final_planning_prompt
    assert "document=D1 -> S2 (new)" in final_planning_prompt
    assert '<source id="S2" document="qms-ref.pdf"' in chat.calls[4][-1].content

    [root] = tracer.roots
    names = [child.name for child in root.children]
    assert names == ["agent_step", "tool", "agent_step", "tool", "agent_step", "tool"] + [
        "agent_step",
        "model",
    ]
    assert root.outputs["intent"] == "compare"
    assert all(child.ended for child in root.children)
    assert "deviation" not in json.dumps([c.inputs for c in root.children])


def test_document_search_is_restricted_to_the_chosen_document(make_client) -> None:
    chat = ScriptedChatProvider(
        [
            step("list_documents"),
            step("search", "reporting hours discovery", "D1"),
            step("finish"),
            answer("Reported within 24 hours [S1].", ids=("S1",)),
        ]
    )
    client = make_client(chat_provider=chat)
    ids = corpus(client)

    body = ask(client).json()

    assert {c["document_id"] for c in body["citations"]} == {ids["ref"]}
    assert '<source id="S2"' not in chat.calls[2][-1].content


def test_explicit_scope_bounds_listed_and_searchable_documents(make_client) -> None:
    chat = ScriptedChatProvider(
        [
            step("list_documents"),
            step("search", "calibration", "D3"),  # outside scope: rejected
            step("search", "calibration twelve months"),  # all in-scope documents
            step("finish"),
            answer("No calibration rule [S1].", ids=("S1",)),
        ]
    )
    client = make_client(chat_provider=chat)
    ids = corpus(client)
    upload(client, CALIBRATION, "aaa-calibration.pdf")

    body = ask(client, document_ids=[ids["sop"], ids["ref"]], mode="compare").json()

    prompt = chat.calls[3][-1].content
    assert "D3" not in prompt.split("TOOL LOG")[0]
    assert "rejected: document must be null or a listed label" in prompt
    assert {c["document_id"] for c in body["citations"]} <= {ids["sop"], ids["ref"]}
    assert "calibrated every twelve months" not in prompt


def test_qa_mode_never_starts_the_agent(make_client) -> None:
    chat = ScriptedChatProvider([answer("Within 48 hours [S1].", ids=("S1",))])
    client = make_client(chat_provider=chat)
    corpus(client)
    assert ask(client, mode="qa").json()["status"] == "answered"
    assert len(chat.calls) == 1 and chat.calls[0][0].content != AGENT_SYSTEM_PROMPT


def test_offline_fake_provider_compares_end_to_end(make_client) -> None:
    client = make_client()
    ids = corpus(client)
    service = client.app.state.chat_service

    result = service.ask("Compare deviation reporting hours after discovery: SOP-001 vs QMS-REF")

    assert result.intent == "compare"
    assert result.status == "answered"
    assert {str(c.document_id) for c in result.retrieved} == {ids["sop"], ids["ref"]}
    assert result.citations


def test_langsmith_environment_does_not_enable_langchain_auto_tracing(
    make_client, monkeypatch
) -> None:
    from langchain_core.tracers import langchain as langchain_tracers

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "not-a-real-key")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "http://127.0.0.1:9")
    created: list[uuid.UUID] = []
    original = langchain_tracers.LangChainTracer.__init__

    def record(self, *args, **kwargs):
        created.append(uuid.uuid4())
        original(self, *args, **kwargs)

    monkeypatch.setattr(langchain_tracers.LangChainTracer, "__init__", record)
    client = make_client()
    corpus(client)

    assert ask(client).status_code == 200
    assert created == []
