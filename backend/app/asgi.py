"""ASGI entrypoint for uvicorn: `uvicorn app.asgi:app`."""

from app.config import get_settings
from app.infrastructure.observability import configure_logging
from app.main import create_app

configure_logging(get_settings().log_level)
app = create_app()
