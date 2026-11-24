import json

import pytest

from app.domain.answers import AnswerValidationError, strip_markers, validate_answer

ALLOWED = {"S1", "S2", "S3"}


def raw(status: str = "answered", answer: str = "Report in 24 h [S1].", ids=("S1",)) -> str:
    return json.dumps({"status": status, "answer": answer, "citation_ids": list(ids)})


def test_valid_answer_merges_listed_and_inline_citations_in_order() -> None:
    result = validate_answer(raw(answer="A [S2]. B [S1].", ids=["S2", "S3"]), ALLOWED)
    assert result.citation_labels == ["S2", "S3", "S1"]


def test_inline_markers_alone_are_accepted() -> None:
    assert validate_answer(raw(answer="Yes [S3].", ids=[]), ALLOWED).citation_labels == ["S3"]


@pytest.mark.parametrize("status", ["insufficient_evidence", "clarification"])
def test_non_answers_drop_citations(status: str) -> None:
    result = validate_answer(raw(status=status, answer="Which SOP?", ids=["S9"]), ALLOWED)
    assert (result.status, result.citation_labels) == (status, [])


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ("not json", "valid JSON"),
        ("[]", "JSON object"),
        (raw(status="certified"), "status"),
        (raw(answer="   "), "non-empty"),
        (raw(answer="x" * 7000), "too long"),
        (json.dumps({"status": "answered", "answer": "x", "citation_ids": "S1"}), "list"),
        (raw(ids=["S9"]), "Unknown citation ids: S9"),
        (raw(answer="Claim [S7].", ids=["S1"]), "Unknown citation ids: S7"),
        (raw(answer="Uncited claim.", ids=[]), "at least one citation"),
    ],
)
def test_rejects_invalid_output(payload: str, reason: str) -> None:
    with pytest.raises(AnswerValidationError, match=reason):
        validate_answer(payload, ALLOWED)


@pytest.mark.parametrize("answer", ["Claim [S1, S9].", "Claim [s9].", "Claim [ S1 ,S9 ]."])
def test_grouped_and_lowercase_markers_are_validated(answer: str) -> None:
    with pytest.raises(AnswerValidationError) as info:
        validate_answer(raw(answer=answer, ids=["S1"]), ALLOWED)
    assert info.value.code == "unknown_citation"


def test_grouped_markers_resolve_to_labels() -> None:
    assert validate_answer(raw(answer="A [S1, s2].", ids=[]), ALLOWED).citation_labels == [
        "S1",
        "S2",
    ]


def test_non_answer_text_has_markers_stripped() -> None:
    result = validate_answer(raw("insufficient_evidence", "Not covered [S1].", ["S1"]), ALLOWED)
    assert result.answer == "Not covered ."


def test_unknown_id_message_never_echoes_arbitrary_model_text() -> None:
    with pytest.raises(AnswerValidationError) as info:
        validate_answer(raw(ids=["Operators report deviations within 24 hours"]), ALLOWED)
    assert "Operators" not in str(info.value)
    assert info.value.code == "unknown_citation"


@pytest.mark.parametrize("answer", [42, None, ["x"]])
def test_rejects_non_string_answer(answer) -> None:
    payload = json.dumps({"status": "answered", "answer": answer, "citation_ids": ["S1"]})
    with pytest.raises(AnswerValidationError):
        validate_answer(payload, ALLOWED)


def test_strip_markers() -> None:
    assert strip_markers("A [S1] and B [S2, S3].") == "A and B ."
