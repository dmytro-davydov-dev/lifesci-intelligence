"""Contract for the comparison agent's model-selected, read-only tools.

The model picks one action per step through strict structured output. Every argument is
validated against allowlists (document labels D1.., source labels S1..) before a tool runs;
there is no shell, web, write or free-form query language.
"""

import json
import uuid
from dataclasses import dataclass
from typing import Literal

Action = Literal["list_documents", "search", "read_passage", "finish"]
ACTIONS: tuple[str, ...] = ("list_documents", "search", "read_passage", "finish")
MAX_QUERY_CHARS = 200

AGENT_STEP_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(ACTIONS)},
        "query": {"type": ["string", "null"]},
        "document": {"type": ["string", "null"]},
        "source": {"type": ["string", "null"]},
    },
    "required": ["action", "query", "document", "source"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class AgentBudget:
    max_steps: int = 6
    max_searches: int = 3
    results_per_search: int = 4


@dataclass(frozen=True)
class ScopedDocument:
    """A ready document the request may read, exposed to the model as `label` (D1, D2...)."""

    label: str
    document_id: uuid.UUID
    name: str
    version: str | None


@dataclass(frozen=True)
class ToolCall:
    action: Action
    query: str | None = None
    document: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class ToolRecord:
    """One executed (or rejected) step, replayed to the model in later prompts."""

    step: int
    call: ToolCall | None
    outcome: str


class AgentStepError(ValueError):
    """Rejected step. `code` is safe to log; the message is shown to the model."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_step(
    raw: str,
    documents: set[str],
    sources: set[str],
    searches_left: int,
) -> ToolCall:
    """Validate one model step against the allowlists and the remaining search budget."""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AgentStepError("invalid_json", "Output is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise AgentStepError("invalid_json", "Output must be a JSON object.")
    action = payload.get("action")
    if action not in ACTIONS:
        raise AgentStepError("invalid_action", "action must be one of " + ", ".join(ACTIONS))

    if action == "search":
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip():
            raise AgentStepError("missing_query", "search needs a non-empty query.")
        if searches_left <= 0:
            raise AgentStepError("search_budget", "The search budget is used up; finish now.")
        document = payload.get("document")
        if document is not None and document not in documents:
            raise AgentStepError(
                "unknown_document",
                "document must be null or a listed label (call list_documents first).",
            )
        return ToolCall("search", query=query.strip()[:MAX_QUERY_CHARS], document=document)

    if action == "read_passage":
        source = payload.get("source")
        if source not in sources:
            raise AgentStepError("unknown_source", "source must be an S label from search results.")
        return ToolCall("read_passage", source=source)

    return ToolCall(action)
