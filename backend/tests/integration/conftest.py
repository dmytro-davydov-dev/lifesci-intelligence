import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    if not TEST_DATABASE_URL:
        if os.environ.get("REQUIRE_INTEGRATION") == "1":
            pytest.fail("REQUIRE_INTEGRATION=1 but TEST_DATABASE_URL is not set")
        pytest.skip("TEST_DATABASE_URL not set; integration tests need a migrated pgvector DB")
    db_engine = create_engine(TEST_DATABASE_URL)
    yield db_engine
    db_engine.dispose()
