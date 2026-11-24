"""Deterministic intent routing between grounded Q&A and multi-document comparison.

A rule, not a model call: routing is cheap, reproducible and testable, and the user can
always force a path with mode=qa or mode=compare. "difference" is deliberately not a
trigger: definition questions ("difference between minor and major deviations") are
single-document Q&A, and forcing them into two-document findings makes them abstain.
"""

import re
from typing import Literal

Intent = Literal["qa", "compare"]
MIN_COMPARE_DOCUMENTS = 2

_COMPARE = re.compile(
    r"\b(?:compar(?:e|es|ed|ing|ison|isons)|versus|vs\.?|align(?:s|ed|ment)?"
    r"|gaps?|discrepanc(?:y|ies)|consistent with|inconsisten(?:t|cy)"
    r"|what changed|changes? between|changed between)\b",
    re.IGNORECASE,
)


def looks_like_comparison(question: str) -> bool:
    return _COMPARE.search(question) is not None


def route_intent(question: str, mode: str, documents_in_scope: int) -> Intent:
    """mode=qa|compare is honoured; auto picks compare only with comparison wording and
    at least two documents to compare."""
    if mode == "qa":
        return "qa"
    if mode == "compare":
        return "compare"
    if documents_in_scope >= MIN_COMPARE_DOCUMENTS and looks_like_comparison(question):
        return "compare"
    return "qa"
