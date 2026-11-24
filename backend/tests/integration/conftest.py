import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text

from app.config import Settings
from app.domain.deadline import Clock
from app.domain.providers import ChatProvider, EmbeddingProvider
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _ensure_database_exists(url: str) -> None:
    target = make_url(url)
    if not (target.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must name a database ending in '_test'")
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target.database},
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        admin.dispose()


def _migrate(url: str) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def database_url() -> str:
    if not TEST_DATABASE_URL:
        if os.environ.get("REQUIRE_INTEGRATION") == "1":
            pytest.fail("REQUIRE_INTEGRATION=1 but TEST_DATABASE_URL is not set")
        pytest.skip("TEST_DATABASE_URL not set; integration tests need PostgreSQL with pgvector")
    _ensure_database_exists(TEST_DATABASE_URL)
    _migrate(TEST_DATABASE_URL)
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    db_engine = create_engine(database_url)
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def clean_db(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE documents, conversations CASCADE"))


@pytest.fixture
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "storage"


ClientFactory = Callable[..., TestClient]


@pytest.fixture
def make_client(database_url: str, clean_db: None, storage_dir: Path) -> Iterator[ClientFactory]:
    """Build API clients sharing one clean test DB and storage dir; optional fake embedder."""
    clients: list[TestClient] = []

    def factory(
        embedder: EmbeddingProvider | None = None,
        chat_provider: ChatProvider | None = None,
        clock: Clock | None = None,
        settings_overrides: dict | None = None,
        **client_kwargs,
    ) -> TestClient:
        settings = Settings(
            database_url=database_url, storage_dir=storage_dir, **(settings_overrides or {})
        )
        app = create_app(settings, embedder=embedder, chat_provider=chat_provider, clock=clock)
        test_client = TestClient(app, **client_kwargs)
        clients.append(test_client.__enter__())
        return test_client

    yield factory
    for test_client in clients:
        test_client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: ClientFactory) -> TestClient:
    return make_client()
