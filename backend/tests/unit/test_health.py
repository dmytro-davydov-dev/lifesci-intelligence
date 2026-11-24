from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client(ready: bool) -> TestClient:
    return TestClient(create_app(Settings(), readiness_check=lambda: ready))


def test_live_returns_ok() -> None:
    response = make_client(ready=False).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ok_when_database_available() -> None:
    response = make_client(ready=True).get("/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_ready_returns_503_when_database_unavailable() -> None:
    response = make_client(ready=False).get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"


def test_ready_reports_unavailable_for_unreachable_database() -> None:
    # Port 1 on loopback refuses connections; the real check must fail fast, not raise.
    settings = Settings(
        database_url="postgresql+psycopg://u:p@127.0.0.1:1/none", db_connect_timeout_seconds=1
    )
    response = TestClient(create_app(settings)).get("/health/ready")
    assert response.status_code == 503
