"""Label integrity of the version-controlled golden dataset against the actual fixtures."""

from collections import Counter
from pathlib import Path

import pytest

from app.corpus import EvalCase, load_golden_dataset, sample_documents
from app.evaluation.evidence import EvidenceCandidate, matches, section_present
from app.infrastructure.pdf import read_pdf_pages
from tests.support.corpus import CORPUS_DIR

CASES = load_golden_dataset(CORPUS_DIR)
ANSWER_STATUSES = {"answered", "insufficient_evidence", "clarification"}
REQUIRED_CATEGORIES = {
    "factual",
    "comparison",
    "unanswerable",
    "ambiguity",
    "injection",
    "extraction",
}
# Categories whose expected facts are quoted verbatim from a single gold passage.
LITERAL_FACT_CATEGORIES = {"factual", "text", "injection"}


def _pages(path: Path) -> dict[int | None, str]:
    if path.suffix == ".pdf":
        return {p.page: p.text for p in read_pdf_pages(path.read_bytes())}
    return {None: path.read_text(encoding="utf-8")}


DOCUMENTS = {d.document_id: _pages(d.path) for d in sample_documents(CORPUS_DIR)}
DOCUMENTS["INJECTION-001"] = _pages(CORPUS_DIR / "adversarial-documents" / "INJECTION-001.txt")


def test_dataset_size_ids_and_categories() -> None:
    assert 12 <= len(CASES) <= 20
    assert len({c.id for c in CASES}) == len(CASES)
    assert {c.category for c in CASES} >= REQUIRED_CATEGORIES
    assert Counter(c.expected_status for c in CASES).keys() <= ANSWER_STATUSES


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_status_and_evidence_are_consistent(case: EvalCase) -> None:
    if case.expected_status == "answered":
        assert case.gold_evidence and case.expected_facts
    else:
        assert not case.gold_evidence and not case.expected_facts


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_gold_evidence_exists_in_fixture_text(case: EvalCase) -> None:
    for ref in case.gold_evidence:
        pages = DOCUMENTS[ref.document_id]
        assert ref.page in pages, f"{ref.document_id} has no page {ref.page}"
        candidate = EvidenceCandidate(ref.document_id, ref.page, pages[ref.page])
        assert matches(candidate, ref), f"section {ref.section} not on {ref}"


@pytest.mark.parametrize(
    "case", [c for c in CASES if c.category in LITERAL_FACT_CATEGORIES], ids=lambda c: c.id
)
def test_literal_facts_appear_in_gold_passage(case: EvalCase) -> None:
    text = " ".join(DOCUMENTS[r.document_id][r.page] for r in case.gold_evidence).lower()
    for fact in case.expected_facts:
        assert fact.lower() in " ".join(text.split()), fact


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_document_scope_and_forbidden_output_are_valid(case: EvalCase) -> None:
    for document_id in case.document_scope or []:
        assert document_id in DOCUMENTS
    scoped_text = " ".join(
        text for d in case.document_scope or [] for text in DOCUMENTS[d].values()
    ).lower()
    for phrase in case.forbidden_output:
        assert phrase.lower() not in " ".join(case.expected_facts).lower()
        # The trap must be live: the forbidden phrase is present in the scoped fixture.
        assert phrase.lower() in scoped_text


def test_section_matching_requires_a_heading() -> None:
    text = " 2. Reporting\n Records within 48 hours. See section 3. for details."
    assert section_present(text, "2")
    assert not section_present(text, "3")
    assert section_present("Section 1. Register review", "1")
    assert not section_present(" 12. Other", "2")
    assert not section_present("Revision 1.0 | CURRENT", "1")
    # Chunk text has whitespace collapsed; headings must still be found.
    assert section_present("operations. 2. Deviation reporting All deviations", "2")


def test_matching_checks_document_and_page() -> None:
    from app.corpus import EvidenceRef

    ref = EvidenceRef("SOP-001-v2", 1, "2")
    assert matches(EvidenceCandidate("SOP-001-v2", 1, " 2. Reporting\n x"), ref)
    assert not matches(EvidenceCandidate("SOP-001-v2", 2, " 2. Reporting\n x"), ref)
    assert not matches(EvidenceCandidate("SOP-001-v1", 1, " 2. Reporting\n x"), ref)
