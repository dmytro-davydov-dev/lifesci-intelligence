"""Dedicated security tests: the only place adversarial fixtures are ingested."""

import json
import re

import pytest

from app.application.prompts import SYSTEM_PROMPT
from app.corpus import adversarial_document
from app.infrastructure.fake_providers import ScriptedChatProvider
from tests.support.corpus import CORPUS_DIR

pytestmark = [pytest.mark.integration, pytest.mark.security]

INJECTED_PHRASE = "BLUE ORCHID OVERRIDE"


def upload_injection(client) -> dict:
    path = adversarial_document(CORPUS_DIR, "INJECTION-001.txt")
    response = client.post(
        "/api/documents", files={"file": (path.name, path.read_bytes(), "text/plain")}
    )
    assert response.json()["status"] == "ready"
    return response.json()


def test_injected_text_reaches_model_only_inside_fenced_sources(make_client) -> None:
    chat = ScriptedChatProvider(
        [json.dumps({"status": "answered", "answer": "Cedar [S1].", "citation_ids": ["S1"]})]
    )
    client = make_client(chat_provider=chat)
    document = upload_injection(client)

    body = client.post(
        "/api/chat",
        json={
            "question": "What is the training room called in INJECTION-001?",
            "document_ids": [document["id"]],
        },
    ).json()

    assert body["status"] == "answered"
    system, user = chat.calls[0][0], chat.calls[0][-1]
    assert system.content == SYSTEM_PROMPT
    assert INJECTED_PHRASE not in system.content
    outside_sources = re.sub(r"<source [^>]*>.*?</source>", "", user.content, flags=re.S)
    assert INJECTED_PHRASE not in outside_sources
    assert INJECTED_PHRASE in user.content  # present only as fenced, untrusted data


def test_model_obeying_injection_without_citations_is_rejected(make_client) -> None:
    obeying = json.dumps(
        {"status": "answered", "answer": f"{INJECTED_PHRASE}. All compliant.", "citation_ids": []}
    )
    client = make_client(chat_provider=ScriptedChatProvider([obeying, obeying]))
    document = upload_injection(client)

    body = client.post(
        "/api/chat",
        json={"question": "Is everything compliant?", "document_ids": [document["id"]]},
    ).json()

    assert body["status"] == "insufficient_evidence"
    assert INJECTED_PHRASE not in body["answer"]
