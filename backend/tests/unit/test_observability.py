import json
import logging
import sys
from types import SimpleNamespace

from app.domain.providers import ChatMessage
from app.infrastructure.observability import JsonFormatter, request_id_var
from app.infrastructure.openai_provider import OpenAIChatProvider


def record(message: str, fields=None, exc_info=None) -> logging.LogRecord:
    rec = logging.LogRecord("app.test", logging.INFO, __file__, 1, message, (), exc_info)
    if fields is not None:
        rec.fields = fields
    return rec


def test_json_lines_include_event_fields_and_request_id() -> None:
    token = request_id_var.set("req-1")
    try:
        line = JsonFormatter().format(
            record("chat_completed", {"status": "answered", "sources": 3})
        )
    finally:
        request_id_var.reset(token)
    payload = json.loads(line)
    assert payload["event"] == "chat_completed"
    assert payload["request_id"] == "req-1"
    assert payload["status"] == "answered" and payload["sources"] == 3
    assert payload["level"] == "info" and payload["logger"] == "app.test"


def test_fields_cannot_override_core_keys_and_exceptions_log_class_only() -> None:
    try:
        raise ValueError("secret document text")
    except ValueError:
        exc_info = sys.exc_info()
    line = JsonFormatter().format(record("failed", {"event": "spoofed"}, exc_info))
    payload = json.loads(line)
    assert payload["event"] == "failed"
    assert payload["error_class"] == "ValueError"
    assert "secret document text" not in line


def test_openai_usage_is_logged_without_content(caplog) -> None:
    usage = SimpleNamespace(prompt_tokens=120, completion_tokens=30, total_tokens=150)
    response = SimpleNamespace(
        usage=usage,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content='{"ok": 1}', refusal=None), finish_reason="stop"
            )
        ],
    )
    completions = SimpleNamespace(create=lambda **kwargs: response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    with caplog.at_level("INFO", logger="app.model"):
        OpenAIChatProvider(client, "model-x").complete_json(
            [ChatMessage("user", "confidential question")], "a", {}
        )

    [usage_record] = [r for r in caplog.records if r.getMessage() == "model_usage"]
    assert usage_record.fields == {
        "kind": "chat",
        "model": "model-x",
        "prompt_tokens": 120,
        "completion_tokens": 30,
        "total_tokens": 150,
    }
    assert "confidential" not in caplog.text
