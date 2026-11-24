"""Structured answer contract and citation validation."""

import json
import re
from dataclasses import dataclass
from typing import Literal

AnswerStatus = Literal["answered", "insufficient_evidence", "clarification"]
ANSWER_STATUSES: tuple[str, ...] = ("answered", "insufficient_evidence", "clarification")

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "I could not find enough evidence in the selected documents to answer this question."
)

# JSON schema sent to the model (strict structured output).
ANSWER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": list(ANSWER_STATUSES)},
        "answer": {"type": "string"},
        "citation_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "answer", "citation_ids"],
    "additionalProperties": False,
}

# Bracketed citation groups like [S1], [s2] or [S1, S3].
MARKER_GROUP = re.compile(r"\[\s*[Ss]\d+(?:\s*,\s*[Ss]\d+)*\s*\]")
_LABEL = re.compile(r"[Ss](\d+)")
_SAFE_LABEL = re.compile(r"^S\d{1,3}$")


class AnswerValidationError(ValueError):
    """Rejected model output. `code` is safe to log; `message` may echo model text."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def strip_markers(text: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", MARKER_GROUP.sub("", text)).strip()


def _markers(answer: str) -> list[str]:
    return [
        f"S{number}" for group in MARKER_GROUP.findall(answer) for number in _LABEL.findall(group)
    ]


@dataclass(frozen=True)
class ValidatedAnswer:
    status: AnswerStatus
    answer: str
    citation_labels: list[str]


def validate_answer(raw: str, allowed_labels: set[str], max_chars: int = 6000) -> ValidatedAnswer:
    """Parse model output; reject unknown citations and uncited answers."""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AnswerValidationError("invalid_json", "Output is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise AnswerValidationError("invalid_json", "Output must be a JSON object.")

    status = payload.get("status")
    answer = payload.get("answer")
    citation_ids = payload.get("citation_ids")
    if status not in ANSWER_STATUSES:
        raise AnswerValidationError(
            "invalid_status", "status must be one of " + ", ".join(ANSWER_STATUSES) + "."
        )
    if not isinstance(answer, str) or not answer.strip():
        raise AnswerValidationError("invalid_answer", "answer must be a non-empty string.")
    if len(answer) > max_chars:
        raise AnswerValidationError("answer_too_long", "answer is too long.")
    if not isinstance(citation_ids, list) or not all(isinstance(c, str) for c in citation_ids):
        raise AnswerValidationError(
            "invalid_citation_ids", "citation_ids must be a list of strings."
        )

    if status != "answered":
        # Non-answers carry no citations, so dangling markers are removed.
        return ValidatedAnswer(status=status, answer=strip_markers(answer), citation_labels=[])

    markers = _markers(answer)
    unknown = sorted({*citation_ids, *markers} - allowed_labels)
    if unknown:
        shown = [label for label in unknown if _SAFE_LABEL.match(label)][:10]
        detail = ", ".join(shown) if shown else "malformed ids"
        raise AnswerValidationError("unknown_citation", f"Unknown citation ids: {detail}.")
    labels = list(dict.fromkeys([*citation_ids, *markers]))
    if not labels:
        raise AnswerValidationError("uncited", "An answered status requires at least one citation.")
    return ValidatedAnswer(status="answered", answer=answer.strip(), citation_labels=labels)
