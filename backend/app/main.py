"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.health import ReadinessCheck
from app.config import Settings, get_settings
from app.infrastructure.db import create_db_engine, database_is_ready


def create_app(
    settings: Settings | None = None, readiness_check: ReadinessCheck | None = None
) -> FastAPI:
    settings = settings or get_settings()
    engine = create_db_engine(settings) if readiness_check is None else None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if engine is not None:
            engine.dispose()

    app = FastAPI(title="LifeSci Intelligence API", version="0.1.0", lifespan=lifespan)

    if engine is not None:

        def readiness_check() -> bool:
            return database_is_ready(engine)

    app.state.readiness_check = readiness_check
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router)
    return app
