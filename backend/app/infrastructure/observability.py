"""Structured JSON logging with request-id correlation.

Log records carry event names, ids, counts, durations and error classes only; never
document text, questions, answers or secrets. Extra fields go in `extra={"fields": {...}}`.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        if request_id := request_id_var.get():
            payload["request_id"] = request_id
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update({k: v for k, v in fields.items() if k not in payload})
        if record.exc_info and record.exc_info[0] is not None:
            payload["error_class"] = record.exc_info[0].__name__  # class only, no message
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Send `app.*` logs to stderr as JSON lines. Idempotent."""
    logger = logging.getLogger("app")
    logger.setLevel(level)
    if not any(getattr(h, "_lifesci_json", False) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._lifesci_json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.propagate = True
