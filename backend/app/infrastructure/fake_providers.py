"""Deterministic offline providers for tests and keyless local runs. Not models."""

import hashlib
import json
import math
import re

from app.config import EMBEDDING_DIMENSIONS
from app.domain.providers import ChatMessage

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "must",
        "of",
        "on",
        "or",
        "the",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "within",
        "should",
        "shall",
    }
)
_QUESTION = re.compile(r"QUESTION:\n(?P<q>.*?)\n\nSOURCES", re.S)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_SOURCE = re.compile(r'<source id="(?P<id>S\d+)"[^>]*>\n(?P<text>.*?)\n</source>', re.S)
_AGENT_QUESTION = re.compile(r"QUESTION:\n(?P<q>.*?)\n\nBUDGET", re.S)
_AGENT_SEARCHES = re.compile(r"searches used (?P<used>\d+) of (?P<max>\d+)")
_AGENT_DOCUMENT = re.compile(r'^(?P<label>D\d+) name="(?P<name>[^"]*)"', re.M)
_AGENT_SEARCHED = re.compile(r"^\d+\. search .*? document=(?P<label>D\d+|all) ->", re.M)
_NAME_TOKEN = re.compile(r"[a-z]+|\d+")


def _content_terms(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


class FakeEmbeddingProvider:
    """Hashed bag-of-words unit vectors: texts sharing terms are similar. No network.

    Useful for deterministic retrieval tests; not a semantic model.
    """

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str], timeout: float | None = None) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            vector[0], norm = 1.0, 1.0
        return [v / norm for v in vector]


class ExtractiveChatProvider:
    """Offline stand-in for a chat model: picks the source sharing most terms with the question
    and quotes its best-matching sentence.

    Abstains when no source shares at least `min_overlap` content terms. Deterministic.
    """

    def __init__(self, min_overlap: int = 2, excerpt_chars: int = 300) -> None:
        self.min_overlap = min_overlap
        self.excerpt_chars = excerpt_chars

    def complete_json(
        self,
        messages: list[ChatMessage],
        schema_name: str,
        schema: dict,
        timeout: float | None = None,
    ) -> str:
        prompt = next((m.content for m in reversed(messages) if m.role == "user"), "")
        if schema_name == "agent_step":
            return json.dumps(self._agent_step(prompt))
        question_match = _QUESTION.search(prompt)
        question_terms = _content_terms(question_match.group("q")) if question_match else set()
        needed = min(self.min_overlap, max(len(question_terms), 1))

        best_id, best_text, best_score = None, "", 0
        for match in _SOURCE.finditer(prompt):
            score = len(question_terms & _content_terms(match.group("text")))
            if score > best_score:
                best_id, best_text, best_score = match.group("id"), match.group("text"), score

        if best_id is None or best_score < needed:
            return json.dumps(
                {
                    "status": "insufficient_evidence",
                    "answer": "The provided sources do not address this question.",
                    "citation_ids": [],
                }
            )
        excerpt = self._best_sentence(best_text, question_terms)
        if len(excerpt) > self.excerpt_chars:
            excerpt = excerpt[: self.excerpt_chars].rstrip() + "..."
        return json.dumps(
            {
                "status": "answered",
                "answer": f'The most relevant passage states: "{excerpt}" [{best_id}]',
                "citation_ids": [best_id],
            }
        )

    @staticmethod
    def _agent_step(prompt: str) -> dict:
        """List documents, search each document named in the question (most name tokens
        first) within the search budget, then finish."""
        step = {"action": "finish", "query": None, "document": None, "source": None}
        if "(not listed yet" in prompt:
            return {**step, "action": "list_documents"}
        question_match = _AGENT_QUESTION.search(prompt)
        question = question_match.group("q") if question_match else ""
        budget = _AGENT_SEARCHES.search(prompt)
        if budget and int(budget.group("used")) >= int(budget.group("max")):
            return step
        wanted = set(_NAME_TOKEN.findall(question.lower()))
        if "reference" in wanted:
            wanted.add("ref")
        searched = set(_AGENT_SEARCHED.findall(prompt))
        ranked = []
        for match in _AGENT_DOCUMENT.finditer(prompt):
            tokens = set(_NAME_TOKEN.findall(match.group("name").lower())) - {"pdf", "txt"}
            overlap = len(tokens & wanted)
            if overlap and match.group("label") not in searched:
                ranked.append((-overlap, int(match.group("label")[1:]), match.group("label")))
        if not ranked:
            return step
        return {**step, "action": "search", "query": question, "document": min(ranked)[2]}

    @staticmethod
    def _best_sentence(text: str, question_terms: set[str]) -> str:
        candidates = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
        return max(candidates, key=lambda s: len(question_terms & _content_terms(s)), default="")


class ScriptedChatProvider:
    """Returns queued replies in order and records every call (for tests)."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls: list[list[ChatMessage]] = []
        self.timeouts: list[float | None] = []

    def complete_json(
        self,
        messages: list[ChatMessage],
        schema_name: str,
        schema: dict,
        timeout: float | None = None,
    ) -> str:
        self.calls.append(list(messages))
        self.timeouts.append(timeout)
        return self.replies.pop(0)
