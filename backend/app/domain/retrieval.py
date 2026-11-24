"""Retrieved evidence and context assembly."""

import uuid
from dataclasses import dataclass, replace

from app.domain.chunking import estimate_tokens

DEFAULT_TOP_K = 8
DEFAULT_CONTEXT_TOKENS = 6000
DEFAULT_CANDIDATE_POOL = 20
DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    page: int | None
    section: str | None
    text: str
    score: float
    ordinal: int = 0  # position within the document; stable tie-break across ingestions


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


def reciprocal_rank_fusion(
    rankings: list[list[RetrievedChunk]],
    top_k: int = DEFAULT_TOP_K,
    k: int = DEFAULT_RRF_K,
) -> list[RetrievedChunk]:
    """Fuse ranked lists by summing 1 / (k + rank); `score` becomes the fused score.

    Ties are broken by best single rank, then document name and ordinal (stable across
    re-ingestion, unlike random chunk ids), so results are reproducible.
    """
    scores: dict[uuid.UUID, float] = {}
    best_rank: dict[uuid.UUID, int] = {}
    chunks: dict[uuid.UUID, RetrievedChunk] = {}
    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
            key = chunk.chunk_id
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            best_rank[key] = min(best_rank.get(key, rank), rank)
            chunks.setdefault(key, chunk)

    def order(key: uuid.UUID) -> tuple:
        chunk = chunks[key]
        return (-scores[key], best_rank[key], chunk.document_name, chunk.ordinal, str(key))

    ordered = sorted(scores, key=order)
    return [replace(chunks[key], score=scores[key]) for key in ordered[:top_k]]
