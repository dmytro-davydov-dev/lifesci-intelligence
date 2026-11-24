"""Retrieval and answer metrics for one evaluation case, plus aggregation."""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.corpus import EvidenceRef
from app.evaluation.evidence import EvidenceCandidate, matches

RECALL_KS = (1, 3, 8)


def recall_at_k(
    retrieved: Sequence[EvidenceCandidate], gold: Sequence[EvidenceRef], k: int
) -> float | None:
    """Fraction of gold references matched by at least one of the top-k chunks."""
    if not gold:
        return None
    top = retrieved[:k]
    return sum(any(matches(c, ref) for c in top) for ref in gold) / len(gold)


def reciprocal_rank(
    retrieved: Sequence[EvidenceCandidate], gold: Sequence[EvidenceRef]
) -> float | None:
    """1 / rank of the first chunk matching any gold reference; 0 if none does."""
    if not gold:
        return None
    for rank, candidate in enumerate(retrieved, start=1):
        if any(matches(candidate, ref) for ref in gold):
            return 1.0 / rank
    return 0.0


def literal_fact_recall(answer: str, facts: Sequence[str]) -> float | None:
    """Share of expected facts appearing verbatim (case/whitespace-insensitive).

    A lower bound on correctness: paraphrased but correct answers score lower.
    """
    if not facts:
        return None
    normalized = " ".join(answer.lower().split())
    return sum(" ".join(f.lower().split()) in normalized for f in facts) / len(facts)


def citation_gold_precision(
    cited: Sequence[EvidenceCandidate], gold: Sequence[EvidenceRef]
) -> float | None:
    """Share of citations that point at a gold passage. Not a semantic-support judgement."""
    if not cited or not gold:
        return None
    return sum(any(matches(c, ref) for ref in gold) for c in cited) / len(cited)


def contains_forbidden(answer: str, forbidden: Sequence[str]) -> bool:
    lowered = answer.lower()
    return any(phrase.lower() in lowered for phrase in forbidden)


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    category: str
    mode: str
    expected_status: str
    status: str
    recall: dict[int, float | None]
    reciprocal_rank: float | None
    fact_recall: float | None
    citation_precision: float | None
    forbidden_leak: bool | None
    latency_ms: float
    error: str | None = None
    citations: int = 0

    @property
    def status_correct(self) -> bool:
        return self.status == self.expected_status


def mean(values: Sequence[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return statistics.fmean(present) if present else None


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0..100)."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q / 100 * len(ordered)) - 1)]


def summarize(results: Sequence[CaseResult]) -> dict[str, float | int | None]:
    answerable = [r for r in results if r.expected_status == "answered"]
    non_answer = [r for r in results if r.expected_status != "answered"]
    guarded = [r for r in results if r.forbidden_leak is not None]
    latencies = [r.latency_ms for r in results if r.error is None]
    summary: dict[str, float | int | None] = {
        "cases": len(results),
        "errors": sum(r.error is not None for r in results),
        **{f"recall@{k}": mean([r.recall.get(k) for r in results]) for k in RECALL_KS},
        "mrr": mean([r.reciprocal_rank for r in results]),
        "status_accuracy": mean([float(r.status_correct) for r in results]),
        # Any non-answer (abstention or clarification) on an answerable case.
        "false_abstention_rate": mean(
            [float(r.status in {"insufficient_evidence", "clarification"}) for r in answerable]
        ),
        "correct_non_answer_rate": mean([float(r.status_correct) for r in non_answer]),
        "cited_non_answer_cases": sum(r.citations > 0 for r in non_answer),
        "literal_fact_recall": mean([r.fact_recall for r in answerable]),
        "citation_gold_precision": mean([r.citation_precision for r in answerable]),
        "injection_leaks": sum(bool(r.forbidden_leak) for r in guarded) if guarded else None,
        "latency_ms_p50": percentile(latencies, 50),
        "latency_ms_p95": percentile(latencies, 95),
    }
    return summary


def gold_document_coverage(
    cited_documents: Sequence[str], gold: Sequence[EvidenceRef]
) -> float | None:
    """Share of gold documents that at least one citation points into."""
    documents = {ref.document_id for ref in gold}
    if not documents:
        return None
    return len(documents & set(cited_documents)) / len(documents)


@dataclass(frozen=True)
class ComparisonCaseResult:
    case_id: str
    category: str
    expected_status: str
    status: str
    intent: str
    # Recall over every passage the agent gathered (its searches, not one ranking).
    evidence_recall: float | None
    gold_document_coverage: float | None
    citation_precision: float | None
    assessments: list[str]
    expected_assessment: str | None
    agent_steps: int
    latency_ms: float
    error: str | None = None

    @property
    def assessment_match(self) -> bool | None:
        """Whether any finding carries the labelled assessment (None when unlabelled)."""
        if self.expected_assessment is None or self.error is not None:
            return None
        return self.expected_assessment in self.assessments


def summarize_comparison(results: Sequence[ComparisonCaseResult]) -> dict[str, Any]:
    labelled = [r.assessment_match for r in results if r.assessment_match is not None]
    latencies = [r.latency_ms for r in results if r.error is None]
    return {
        "cases": len(results),
        "errors": sum(r.error is not None for r in results),
        "routed_to_compare": sum(r.intent == "compare" for r in results),
        "status_accuracy": mean([float(r.status == r.expected_status) for r in results]),
        "evidence_recall": mean([r.evidence_recall for r in results]),
        "gold_document_coverage": mean([r.gold_document_coverage for r in results]),
        "citation_gold_precision": mean([r.citation_precision for r in results]),
        "assessment_accuracy": mean([float(m) for m in labelled]),
        "labelled_cases": len(labelled),
        "mean_agent_steps": mean([float(r.agent_steps) for r in results if r.error is None]),
        "latency_ms_p50": percentile(latencies, 50),
        "latency_ms_p95": percentile(latencies, 95),
    }
