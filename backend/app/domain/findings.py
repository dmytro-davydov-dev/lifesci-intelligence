"""Structured comparison findings: schema and validation.

Findings say what the cited sources show, never that a procedure is compliant. A
`supported` or `potential_gap` finding must cite passages from at least two different
documents, so a one-sided reading cannot be presented as a comparison.
"""

import json
import uuid

from app.domain.answers import (
    ANSWER_STATUSES,
    ASSESSMENTS,
    AnswerValidationError,
    Finding,
    ValidatedAnswer,
    markers,
    validate_answer,
)

MAX_FINDINGS = 8
MAX_TOPIC_CHARS = 200
MAX_EXPLANATION_CHARS = 1500

FINDINGS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": list(ANSWER_STATUSES)},
        "answer": {"type": "string"},
        "citation_ids": {"type": "array", "items": {"type": "string"}},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "assessment": {"type": "string", "enum": list(ASSESSMENTS)},
                    "explanation": {"type": "string"},
                    "citation_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["topic", "assessment", "explanation", "citation_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["status", "answer", "citation_ids", "findings"],
    "additionalProperties": False,
}


def _text(item: dict, key: str, limit: int) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AnswerValidationError("invalid_finding", f"Each finding needs a non-empty {key}.")
    if len(value) > limit:
        raise AnswerValidationError("invalid_finding", f"A finding {key} is too long.")
    return value.strip()


def _finding(item: object, label_documents: dict[str, uuid.UUID]) -> Finding:
    if not isinstance(item, dict):
        raise AnswerValidationError("invalid_finding", "Each finding must be an object.")
    topic = _text(item, "topic", MAX_TOPIC_CHARS)
    if markers(topic):
        raise AnswerValidationError(
            "invalid_finding", "Put citations in the explanation, not in the topic."
        )
    explanation = _text(item, "explanation", MAX_EXPLANATION_CHARS)
    assessment = item.get("assessment")
    if assessment not in ASSESSMENTS:
        raise AnswerValidationError(
            "invalid_assessment", "assessment must be one of " + ", ".join(ASSESSMENTS) + "."
        )
    citation_ids = item.get("citation_ids")
    if not isinstance(citation_ids, list) or not all(isinstance(c, str) for c in citation_ids):
        raise AnswerValidationError(
            "invalid_citation_ids", "Each finding's citation_ids must be a list of strings."
        )
    labels = list(dict.fromkeys([*citation_ids, *markers(explanation)]))
    if unknown := [label for label in labels if label not in label_documents]:
        shown = ", ".join(label for label in unknown if label[:1] == "S" and len(label) <= 4)
        raise AnswerValidationError(
            "unknown_citation", f"Unknown citation ids in findings: {shown or 'malformed ids'}."
        )
    if assessment != "insufficient_evidence":
        documents = {label_documents[label] for label in labels}
        if len(documents) < 2:
            raise AnswerValidationError(
                "one_sided_finding",
                f'A "{assessment}" finding must cite sources from at least two different '
                'documents; otherwise use "insufficient_evidence".',
            )
    return Finding(topic, assessment, explanation, labels)


def validate_comparison(
    raw: str, label_documents: dict[str, uuid.UUID], max_chars: int = 6000
) -> ValidatedAnswer:
    """Validate the answer like Q&A, then each finding; citations are the union of both."""
    base = validate_answer(raw, set(label_documents), max_chars)
    if base.status != "answered":
        return base
    findings_raw = json.loads(raw).get("findings")
    if not isinstance(findings_raw, list) or not findings_raw:
        raise AnswerValidationError("no_findings", "An answered comparison needs findings.")
    if len(findings_raw) > MAX_FINDINGS:
        raise AnswerValidationError("too_many_findings", f"Return at most {MAX_FINDINGS} findings.")
    findings = [_finding(item, label_documents) for item in findings_raw]
    labels = list(
        dict.fromkeys(
            [*base.citation_labels, *(label for f in findings for label in f.citation_labels)]
        )
    )
    return ValidatedAnswer("answered", base.answer, labels, findings)
