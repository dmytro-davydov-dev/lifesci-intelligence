"""Liveness and readiness endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/health", tags=["health"])

ReadinessCheck = Callable[[], bool]


def get_readiness_check(request: Request) -> ReadinessCheck:
    return request.app.state.readiness_check


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(check: Annotated[ReadinessCheck, Depends(get_readiness_check)]) -> JSONResponse:
    if check():
        return JSONResponse({"status": "ok", "database": "ok"})
    return JSONResponse({"status": "unavailable", "database": "unavailable"}, status_code=503)
