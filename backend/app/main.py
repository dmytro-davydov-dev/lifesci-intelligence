"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from app.api import documents, health
from app.api.errors import install_error_handling
from app.api.health import ReadinessCheck
from app.application.documents import DocumentService
from app.config import Settings, get_settings
from app.domain.documents import MAX_UPLOAD_BYTES
from app.infrastructure.db import create_db_engine, database_is_ready
from app.infrastructure.pdf import count_pdf_pages
from app.infrastructure.storage import LocalFileStorage

# Multipart framing overhead allowed on top of the file size limit.
_MULTIPART_OVERHEAD_BYTES = 64 * 1024


def create_app(
    settings: Settings | None = None, readiness_check: ReadinessCheck | None = None
) -> FastAPI:
    settings = settings or get_settings()
    engine = create_db_engine(settings)
    session_factory = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(title="LifeSci Intelligence API", version="0.1.0", lifespan=lifespan)
    app.state.readiness_check = readiness_check or (lambda: database_is_ready(engine))
    app.state.document_service = DocumentService(
        session_factory, LocalFileStorage(settings.storage_dir), count_pdf_pages
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
    return app
