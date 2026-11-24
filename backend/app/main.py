"""FastAPI application factory."""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from app.api import chat, documents, health
from app.api.errors import install_error_handling
from app.api.health import ReadinessCheck
from app.application.chat import ChatService, ChatSettings
from app.application.documents import DocumentService
from app.application.ingestion import IngestionService
from app.config import Settings, get_settings
from app.domain.deadline import Clock
from app.domain.documents import MAX_UPLOAD_BYTES
from app.domain.providers import ChatProvider, EmbeddingProvider
from app.infrastructure.db import create_db_engine, database_is_ready
from app.infrastructure.pdf import read_pdf_pages
from app.infrastructure.providers import build_chat_provider, build_embedding_provider
from app.infrastructure.storage import LocalFileStorage

# Multipart framing overhead allowed on top of the file size limit.
_MULTIPART_OVERHEAD_BYTES = 64 * 1024


def create_app(
    settings: Settings | None = None,
    readiness_check: ReadinessCheck | None = None,
    embedder: EmbeddingProvider | None = None,
    chat_provider: ChatProvider | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    embedder = embedder or build_embedding_provider(settings)
    chat_provider = chat_provider or build_chat_provider(settings)
    engine = create_db_engine(settings)
    session_factory = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(title="LifeSci Intelligence API", version="0.1.0", lifespan=lifespan)
    app.state.readiness_check = readiness_check or (lambda: database_is_ready(engine))
    ingestion = IngestionService(
        session_factory,
        embedder,
        settings.embedding_batch_size,
        settings.ingestion_deadline_seconds,
    )
    app.state.document_service = DocumentService(
        session_factory, LocalFileStorage(settings.storage_dir), read_pdf_pages, ingestion
    )

    app.state.chat_service = ChatService(
        session_factory,
        embedder,
        chat_provider,
        ChatSettings(
            top_k=settings.retrieval_top_k,
            context_max_tokens=settings.context_max_tokens,
            history_max_messages=settings.history_max_messages,
            history_message_max_chars=settings.history_message_max_chars,
            request_deadline_seconds=settings.request_deadline_seconds,
        ),
        clock=clock or time.monotonic,
    )

    install_error_handling(app, max_request_bytes=MAX_UPLOAD_BYTES + _MULTIPART_OVERHEAD_BYTES)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID"],
    )
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(chat.router)
    return app
