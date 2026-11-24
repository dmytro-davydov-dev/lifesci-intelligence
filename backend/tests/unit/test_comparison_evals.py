import json

import pytest

from app.corpus import EvidenceRef, load_golden_dataset
from app.evaluation.metrics import (
    ComparisonCaseResult,
    gold_document_coverage,
    summarize_comparison,
)
from app.evaluation.run import (
    COMPARISON_LABELS,
    EvaluationSetupError,
    load_comparison_labels,
)
from tests.support.corpus import CORPUS_DIR

CASES = load_golden_dataset(CORPUS_DIR)


def result(case_id="E06", assessments=(), expected="potential_gap", **overrides):
    values = {
        "case_id": case_id,
        "category": "comparison",
        "expected_status": "answered",
        "status": "answered",
        "intent": "compare",
        "evidence_recall": 1.0,
        "gold_document_coverage": 0.5,
        "citation_precision": 1.0,
        "assessments": list(assessments),
        "expected_assessment": expected,
        "agent_steps": 4,
        "latency_ms": 10.0,
        **overrides,
    }
    return ComparisonCaseResult(**values)


def test_repository_labels_cover_exactly_the_comparison_cases() -> None:
    labels = load_comparison_labels(COMPARISON_LABELS, CASES)
    assert labels == {
        "E06": "potential_gap",
        "E07": "potential_gap",
        "E08": "potential_gap",
        "E09": "supported",
        "E10": None,
    }


@pytest.mark.parametrize(
    "cases",
    [
        {"E06": {"expected_assessment": "potential_gap"}},  # missing cases
        {
            **{c: {"expected_assessment": None} for c in ("E06", "E07", "E08", "E09", "E10")},
            "E09": {"expected_assessment": "compliant"},
        },
    ],
)
def test_invalid_label_files_are_rejected(tmp_path, cases) -> None:
    path = tmp_path / "labels.json"
    path.write_text(json.dumps({"cases": cases}))
    with pytest.raises(EvaluationSetupError):
        load_comparison_labels(path, CASES)


def test_gold_document_coverage_counts_distinct_gold_documents() -> None:
    gold = [EvidenceRef("SOP-001-v2", 1, "2"), EvidenceRef("QMS-REF-001", 1, "2")]
    assert gold_document_coverage(["SOP-001-v2", "SOP-001-v2"], gold) == 0.5
    assert gold_document_coverage(["SOP-001-v2", "QMS-REF-001", "SOP-004"], gold) == 1.0
    assert gold_document_coverage(["SOP-001-v2"], []) is None


def test_assessment_match_and_summary() -> None:
    rows = [
        result("E06", ["potential_gap", "insufficient_evidence"]),
        result("E09", ["insufficient_evidence"], expected="supported", agent_steps=2),
        result("E10", [], expected=None, status="insufficient_evidence"),
    ]
    assert [r.assessment_match for r in rows] == [True, False, None]
    summary = summarize_comparison(rows)
    assert summary["assessment_accuracy"] == 0.5
    assert summary["labelled_cases"] == 2
    assert summary["status_accuracy"] == pytest.approx(2 / 3)
    assert summary["mean_agent_steps"] == pytest.approx(10 / 3)
    assert summary["routed_to_compare"] == 3


def test_errors_are_excluded_from_assessment_scoring() -> None:
    row = result(status="error", error="ChatError", assessments=[])
    assert row.assessment_match is None
    assert summarize_comparison([row])["errors"] == 1
