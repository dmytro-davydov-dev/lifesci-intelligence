"""Retrieved evidence and context assembly."""

import uuid
from dataclasses import dataclass

from app.domain.chunking import estimate_tokens

DEFAULT_TOP_K = 8
DEFAULT_CONTEXT_TOKENS = 6000


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    page: int | None
    section: str | None
    text: str
    score: float


@dataclass(frozen=True)
class Source:
    """A retrieved chunk exposed to the model under a short allowlisted label (S1, S2...)."""

    label: str
    chunk: RetrievedChunk


def select_sources(
    chunks: list[RetrievedChunk], max_tokens: int = DEFAULT_CONTEXT_TOKENS
) -> list[Source]:
    """Keep chunks in rank order until the context budget is spent."""
    sources: list[Source] = []
    used = 0
    for chunk in chunks:
        cost = estimate_tokens(chunk.text)
        if used + cost > max_tokens:
            break
        used += cost
        sources.append(Source(label=f"S{len(sources) + 1}", chunk=chunk))
    return sources
