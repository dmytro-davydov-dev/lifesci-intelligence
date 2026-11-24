"""Vector search over chunks of ready documents."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.retrieval import RetrievedChunk
from app.infrastructure.models import Chunk, Document


def vector_search(
    session: Session,
    query_vector: list[float],
    document_ids: list[uuid.UUID] | None,
    top_k: int,
) -> list[RetrievedChunk]:
    """Exact cosine search; only `ready` documents, optionally restricted to document_ids."""
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
    statement = (
        select(Chunk, Document.name, distance)
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.status == "ready")
        .order_by(distance, Chunk.id)
        .limit(top_k)
    )
    if document_ids is not None:
        statement = statement.where(Chunk.document_id.in_(document_ids))
    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_name=name,
            page=chunk.page,
            section=chunk.section,
            text=chunk.text,
            score=1.0 - float(dist),
        )
        for chunk, name, dist in session.execute(statement)
    ]
