from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.documents import MAX_UPLOAD_BYTES
from app.main import create_app

client = TestClient(create_app(Settings(), readiness_check=lambda: True))


def test_generates_request_id_when_missing() -> None:
    response = client.get("/health/live")
    assert len(response.headers["X-Request-ID"]) == 32


def test_echoes_safe_request_id_and_replaces_unsafe_one() -> None:
    assert (
        client.get("/health/live", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"]
        == "abc-123"
    )
    unsafe = client.get("/health/live", headers={"X-Request-ID": "bad id<script>"})
    assert unsafe.headers["X-Request-ID"] != "bad id<script>"


def test_unknown_route_uses_error_envelope() -> None:
    response = client.get("/nope", headers={"X-Request-ID": "req-1"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "request_id": "req-1"}
    }


def test_invalid_document_id_is_rejected_before_database_access() -> None:
    response = client.get("/api/documents/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_oversized_request_rejected_by_content_length() -> None:
    response = client.post(
        "/api/documents",
        content=b"x",
        headers={"Content-Length": str(MAX_UPLOAD_BYTES * 2), "Content-Type": "text/plain"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_unexpected_error_returns_envelope_with_cors_headers() -> None:
    app = create_app(Settings(), readiness_check=lambda: True)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret detail")

    response = TestClient(app, raise_server_exceptions=False).get(
        "/boom", headers={"Origin": "http://127.0.0.1:3000", "X-Request-ID": "r-500"}
    )
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred.",
            "request_id": "r-500",
        }
    }


def test_method_not_allowed_keeps_allow_header() -> None:
    response = client.delete("/health/live")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert "GET" in response.headers["allow"]
