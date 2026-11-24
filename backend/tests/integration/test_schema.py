import uuid

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.infrastructure.db import database_is_ready
from app.infrastructure.fake_providers import FakeEmbeddingProvider
from app.infrastructure.models import Base, Chunk, Document

pytestmark = pytest.mark.integration


def test_database_is_ready(engine: Engine) -> None:
    assert database_is_ready(engine)


def test_vector_extension_installed(engine: Engine) -> None:
    with engine.connect() as connection:
        found = connection.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
    assert found == 1


def test_migrated_schema_matches_orm_models(engine: Engine) -> None:
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []


def test_chunk_roundtrip_supports_cosine_search_and_fts(engine: Engine) -> None:
    embedder = FakeEmbeddingProvider()
    with Session(engine) as session, session.begin():
        document = Document(
            name="synthetic.txt",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            media_type="text/plain",
            storage_key=uuid.uuid4().hex,
            status="ready",
        )
        session.add(document)
        session.flush()
        texts = ["Deviations must be reported within 24 hours.", "CAPA owners review trends."]
        for ordinal, (chunk_text, vector) in enumerate(
            zip(texts, embedder.embed(texts), strict=True)
        ):
            session.add(
                Chunk(document_id=document.id, ordinal=ordinal, text=chunk_text, embedding=vector)
            )
        session.flush()

        query_vector = embedder.embed([texts[0]])[0]
        nearest = session.scalars(
            select(Chunk)
            .where(Chunk.document_id == document.id)
            .order_by(Chunk.embedding.cosine_distance(query_vector))
            .limit(1)
        ).one()
        assert nearest.ordinal == 0

        fts_hit = session.scalars(
            select(Chunk.ordinal).where(
                Chunk.document_id == document.id,
                Chunk.search.op("@@")(text("plainto_tsquery('english', 'reported')")),
            )
        ).all()
        assert fts_hit == [0]
        session.rollback()
