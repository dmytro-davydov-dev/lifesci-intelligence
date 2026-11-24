import json
import uuid

import pytest

from app.domain.answers import AnswerValidationError
from app.domain.findings import MAX_FINDINGS, validate_comparison

SOP, REF = uuid.uuid4(), uuid.uuid4()
LABELS = {"S1": SOP, "S2": SOP, "S3": REF}


def finding(assessment="potential_gap", ids=("S1", "S3"), explanation=None, topic="Reporting"):
    return {
        "topic": topic,
        "assessment": assessment,
        "explanation": explanation if explanation is not None else "48 h versus 24 h.",
        "citation_ids": list(ids),
    }


def raw(findings, status="answered", answer="Summary [S1].", ids=("S1",)) -> str:
    return json.dumps(
        {"status": status, "answer": answer, "citation_ids": list(ids), "findings": findings}
    )


def code(output: str) -> str:
    with pytest.raises(AnswerValidationError) as info:
        validate_comparison(output, LABELS)
    return info.value.code


def test_valid_findings_and_citation_union() -> None:
    result = validate_comparison(
        raw(
            [
                finding(),
                finding("supported", ids=(), explanation="Both need QA approval [S2] [S3]."),
                finding("insufficient_evidence", ids=()),
            ]
        ),
        LABELS,
    )
    assert result.status == "answered"
    assert [f.assessment for f in result.findings] == [
        "potential_gap",
        "supported",
        "insufficient_evidence",
    ]
    assert result.findings[1].citation_labels == ["S2", "S3"]
    assert result.findings[2].citation_labels == []
    assert result.citation_labels == ["S1", "S3", "S2"]


@pytest.mark.parametrize("assessment", ["supported", "potential_gap"])
def test_one_sided_findings_are_rejected(assessment: str) -> None:
    assert code(raw([finding(assessment, ids=("S1", "S2"))])) == "one_sided_finding"
    assert code(raw([finding(assessment, ids=())])) == "one_sided_finding"


def test_unknown_citations_in_findings_are_rejected() -> None:
    assert code(raw([finding(ids=("S1", "S9"))])) == "unknown_citation"
    assert code(raw([finding(explanation="See [S7].", ids=("S1", "S3"))])) == "unknown_citation"


@pytest.mark.parametrize(
    ("findings", "expected"),
    [
        ([], "no_findings"),
        (None, "no_findings"),
        ([finding()] * (MAX_FINDINGS + 1), "too_many_findings"),
        (["text"], "invalid_finding"),
        ([finding(topic=" ")], "invalid_finding"),
        ([finding(explanation="x" * 5000)], "invalid_finding"),
        ([finding("compliant")], "invalid_assessment"),
        ([{**finding(), "citation_ids": "S1"}], "invalid_citation_ids"),
    ],
)
def test_malformed_findings_are_rejected(findings, expected: str) -> None:
    assert code(raw(findings)) == expected


def test_answer_rules_still_apply() -> None:
    assert code(raw([finding()], answer="Uncited summary.", ids=())) == "uncited"
    assert code(raw([finding()], ids=("S5",))) == "unknown_citation"


def test_non_answers_drop_findings() -> None:
    result = validate_comparison(
        raw([finding()], status="insufficient_evidence", answer="Not enough [S1].", ids=()),
        LABELS,
    )
    assert (result.status, result.findings, result.citation_labels) == (
        "insufficient_evidence",
        [],
        [],
    )
    assert result.answer == "Not enough ."
