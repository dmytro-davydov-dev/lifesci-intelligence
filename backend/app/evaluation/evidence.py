"""Match retrieved chunks against gold evidence labels.

Gold labels use stable fixture document ids, 1-based PDF pages (null for text) and logical
section numbers. Section numbers are matched by headings ("2. Reporting",
"Section 1. Register review"), not by chunk ids, so labels survive re-chunking.
"""

import re
from dataclasses import dataclass

from app.corpus import EvidenceRef


@dataclass(frozen=True)
class EvidenceCandidate:
    """A retrieved chunk expressed in fixture terms."""

    document_id: str
    page: int | None
    text: str


def section_present(text: str, section: str) -> bool:
    # Works on raw page text and on whitespace-normalised chunk text: the number must not
    # continue another number ("12.", "1.0") and the heading starts with a capital letter.
    heading = re.compile(rf"(?<![\w.])(?:Section\s+)?{re.escape(section)}\.\s+[A-Z]")
    return heading.search(text) is not None


def matches(candidate: EvidenceCandidate, gold: EvidenceRef) -> bool:
    if candidate.document_id != gold.document_id:
        return False
    if gold.page is not None and candidate.page != gold.page:
        return False
    return gold.section is None or section_present(candidate.text, gold.section)
