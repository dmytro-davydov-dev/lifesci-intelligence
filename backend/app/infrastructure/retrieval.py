"""Vector, keyword and hybrid search over chunks of ready documents."""

import re
import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.domain.retrieval import (
    DEFAULT_CANDIDATE_POOL,
    DEFAULT_RRF_K,
    RetrievedChunk,
    reciprocal_rank_fusion,
)
from app.infrastructure.models import Chunk, Document

_TERM = re.compile(r"[A-Za-z0-9]+")
MAX_QUERY_TERMS = 32


def _scoped(statement: Select, document_ids: list[uuid.UUID] | None) -> Select:
    statement = statement.join(Document, Document.id == Chunk.document_id).where(
        Document.status == "ready"
    )
    if document_ids is not None:
        statement = statement.where(Chunk.document_id.in_(document_ids))
    return statement


def _retrieved(chunk: Chunk, name: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        document_name=name,
        page=chunk.page,
        section=chunk.section,
        text=chunk.text,
        score=score,
    )


def vector_search(
    session: Session,
    query_vector: list[float],
    document_ids: list[uuid.UUID] | None,
    top_k: int,
) -> list[RetrievedChunk]:
    """Exact cosine search; only `ready` documents, optionally restricted to document_ids."""
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
    statement = _scoped(select(Chunk, Document.name, distance), document_ids)
    statement = statement.order_by(distance, Chunk.id).limit(top_k)
    return [
        _retrieved(chunk, name, 1.0 - float(dist))
        for chunk, name, dist in session.execute(statement)
    ]


def or_tsquery(question: str) -> str:
    """Build a to_tsquery string that ORs the question's alphanumeric terms.

    Only [A-Za-z0-9] runs are kept, so user text cannot inject tsquery operators.
    """
    terms = list(dict.fromkeys(term.lower() for term in _TERM.findall(question)))
    return " | ".join(terms[:MAX_QUERY_TERMS])


def keyword_search(
    session: Session,
    question: str,
    document_ids: list[uuid.UUID] | None,
    top_k: int,
) -> list[RetrievedChunk]:
    """Full-text search (English config) ranked by ts_rank_cd; same filters as vector search."""
    expression = or_tsquery(question)
    if not expression:
        return []
    query = func.to_tsquery("english", expression)
    rank = func.ts_rank_cd(Chunk.search, query).label("rank")
    statement = _scoped(select(Chunk, Document.name, rank), document_ids)
    statement = (
        statement.where(Chunk.search.bool_op("@@")(query))
        .order_by(rank.desc(), Chunk.id)
        .limit(top_k)
    )
    return [
        _retrieved(chunk, name, float(score)) for chunk, name, score in session.execute(statement)
    ]


def hybrid_search(
    session: Session,
    query_vector: list[float],
    question: str,
    document_ids: list[uuid.UUID] | None,
    top_k: int,
    candidate_pool: int = DEFAULT_CANDIDATE_POOL,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[RetrievedChunk]:
    """Vector and keyword candidate pools fused with reciprocal rank fusion."""
    vector = vector_search(session, query_vector, document_ids, candidate_pool)
    keyword = keyword_search(session, question, document_ids, candidate_pool)
    return reciprocal_rank_fusion([vector, keyword], top_k=top_k, k=rrf_k)
