"""Trace payload redaction policy.

Default: metadata only (lengths, counts, ids, labels, scores, statuses, error codes).
With include_content=True (approved public/synthetic fixtures only), question, answer
and source text are added. Secrets and provider messages are never traced.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from app.domain.retrieval import RetrievedChunk, Source


@dataclass(frozen=True)
class TracePayloads:
    include_content: bool = False

    def chat_inputs(
        self, question: str, document_ids: list[uuid.UUID] | None, mode: str
    ) -> dict[str, Any]:
        inputs: dict[str, Any] = {
            "question_chars": len(question),
            "document_scope": None if document_ids is None else len(document_ids),
            "mode": mode,
        }
        if self.include_content:
            inputs["question"] = question
        return inputs

    def chat_outputs(self, status: str, answer: str, citation_labels: list[str]) -> dict[str, Any]:
        outputs: dict[str, Any] = {
            "status": status,
            "answer_chars": len(answer),
            "citations": citation_labels,
        }
        if self.include_content:
            outputs["answer"] = answer
        return outputs

    def retrieved(self, chunks: list[RetrievedChunk]) -> dict[str, Any]:
        return {"documents": [self._chunk(chunk) for chunk in chunks]}

    def sources(self, sources: list[Source], attempt: int) -> dict[str, Any]:
        return {
            "attempt": attempt,
            "sources": [{"label": s.label, **self._chunk(s.chunk)} for s in sources],
        }

    def _chunk(self, chunk: RetrievedChunk) -> dict[str, Any]:
        item: dict[str, Any] = {
            "chunk_id": str(chunk.chunk_id),
            "document_id": str(chunk.document_id),
            "page": chunk.page,
            "score": round(chunk.score, 6),
            "chars": len(chunk.text),
        }
        if self.include_content:
            item["text"] = chunk.text
        return item
