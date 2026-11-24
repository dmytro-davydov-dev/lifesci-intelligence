"""Consistent error envelope and request IDs."""

import logging
import re
import uuid
from collections.abc import Awaitable, Callable, Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

logger = logging.getLogger("app.api")

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = request_id_of(request)
    return JSONResponse(
        {"error": {"code": code, "message": message, "request_id": request_id}},
        status_code=status_code,
        headers={**(headers or {}), REQUEST_ID_HEADER: request_id},
    )


def _internal_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_error request_id=%s error_class=%s",
        request_id_of(request),
        type(exc).__name__,
    )
    return error_response(request, 500, "internal_error", "An unexpected error occurred.")


def install_error_handling(app: FastAPI, max_request_bytes: int) -> None:
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request.state.request_id = (
            incoming if _SAFE_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        )
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_request_bytes:
            return error_response(request, 413, "file_too_large", "Request body is too large.")
        try:
            response = await call_next(request)
        except Exception as exc:
            # Handled here (inside CORSMiddleware) so browsers can read the 500 envelope.
            return _internal_error(request, exc)
        response.headers[REQUEST_ID_HEADER] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(p) for p in err["loc"][1:]) for err in exc.errors()})
        message = "Invalid request" + (f": {', '.join(fields)}." if fields else ".")
        return error_response(request, 422, "validation_error", message)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_response(request, exc.status_code, code, str(exc.detail), exc.headers)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        return _internal_error(request, exc)
