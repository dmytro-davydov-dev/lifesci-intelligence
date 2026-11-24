import pytest

from app.corpus import load_golden_dataset
from app.domain.intent import looks_like_comparison, route_intent
from tests.support.corpus import CORPUS_DIR


@pytest.mark.parametrize(
    "question",
    [
        "Compare reporting deadlines in SOP-001 and the reference.",
        "Does SOP-003 align with the reference threshold?",
        "What changed between revision 1 and 2?",
        "Is there a gap in CAPA verification?",
        "SOP-001 vs QMS-REF-001 reporting",
        "What are the differences in closure approval?",
    ],
)
def test_comparison_wording_is_detected(question: str) -> None:
    assert looks_like_comparison(question)


@pytest.mark.parametrize(
    "question",
    [
        "How soon must a deviation be recorded?",
        "Which different roles approve CAPA?",  # "different" is not a comparison request
        "What is the retention period?",
    ],
)
def test_plain_questions_are_not_comparisons(question: str) -> None:
    assert not looks_like_comparison(question)


def test_explicit_mode_wins_over_wording() -> None:
    assert route_intent("Compare A and B", "qa", 5) == "qa"
    assert route_intent("When is it reported?", "compare", 5) == "compare"


def test_auto_needs_two_documents_to_compare() -> None:
    assert route_intent("Compare A and B", "auto", 1) == "qa"
    assert route_intent("Compare A and B", "auto", 2) == "compare"


def test_golden_dataset_routes_comparison_and_version_cases_only() -> None:
    for case in load_golden_dataset(CORPUS_DIR):
        expected = "compare" if case.category in {"comparison", "version"} else "qa"
        assert route_intent(case.question, "auto", 7) == expected, case.id
