import pytest

from app.corpus import EvidenceRef
from app.evaluation.evidence import EvidenceCandidate
from app.evaluation.metrics import (
    CaseResult,
    citation_gold_precision,
    contains_forbidden,
    literal_fact_recall,
    percentile,
    recall_at_k,
    reciprocal_rank,
    summarize,
)

SOP_2 = EvidenceCandidate("SOP-001-v2", 1, "1. Scope x. 2. Reporting Within 48 hours.")
REF_2 = EvidenceCandidate("QMS-REF-001", 1, "2. Deviation reporting Within 24 hours.")
OTHER = EvidenceCandidate("SOP-004", 1, "1. Approval QA approves.")
GOLD = [EvidenceRef("SOP-001-v2", 1, "2"), EvidenceRef("QMS-REF-001", 1, "2")]


def test_recall_counts_gold_refs_covered_in_top_k() -> None:
    retrieved = [OTHER, SOP_2, REF_2]
    assert recall_at_k(retrieved, GOLD, 1) == 0
    assert recall_at_k(retrieved, GOLD, 2) == 0.5
    assert recall_at_k(retrieved, GOLD, 8) == 1
    assert recall_at_k(retrieved, [], 8) is None


def test_reciprocal_rank_uses_first_relevant_chunk() -> None:
    assert reciprocal_rank([OTHER, OTHER, REF_2], GOLD) == pytest.approx(1 / 3)
    assert reciprocal_rank([OTHER], GOLD) == 0
    assert reciprocal_rank([OTHER], []) is None


def test_literal_fact_recall_is_case_and_whitespace_insensitive() -> None:
    assert literal_fact_recall("Within 48\nHours [S1].", ["48 hours", "QA"]) == 0.5
    assert literal_fact_recall("anything", []) is None


def test_citation_precision_and_forbidden_output() -> None:
    assert citation_gold_precision([SOP_2, OTHER], GOLD) == 0.5
    assert citation_gold_precision([], GOLD) is None
    assert contains_forbidden("blue orchid override", ["BLUE ORCHID OVERRIDE"])
    assert not contains_forbidden("Cedar", ["BLUE ORCHID OVERRIDE"])


def test_percentile_nearest_rank() -> None:
    assert percentile([10, 20, 30, 40], 50) == 20
    assert percentile([10, 20, 30, 40], 95) == 40
    assert percentile([], 50) is None


def result(case_id, expected, status, rr=None, leak=None, error=None) -> CaseResult:
    return CaseResult(
        case_id,
        "c",
        "hybrid",
        expected,
        status,
        {1: rr, 3: rr, 8: rr},
        rr,
        None,
        None,
        leak,
        5.0,
        error,
    )


def test_summary_separates_answerable_and_non_answer_cases() -> None:
    summary = summarize(
        [
            result("A", "answered", "answered", rr=1.0),
            result("B", "answered", "insufficient_evidence", rr=0.0),
            result("C", "insufficient_evidence", "insufficient_evidence"),
            result("D", "clarification", "answered", leak=False),
        ]
    )
    assert summary["mrr"] == 0.5
    assert summary["status_accuracy"] == 0.5
    assert summary["false_abstention_rate"] == 0.5
    assert summary["correct_non_answer_rate"] == 0.5
    assert summary["injection_leaks"] == 0
    assert summary["errors"] == 0
