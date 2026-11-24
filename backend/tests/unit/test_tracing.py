import uuid
from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from app.application.trace_payloads import TracePayloads
from app.config import Settings
from app.domain.retrieval import RetrievedChunk, Source
from app.domain.tracing import NoopSpan, NoopTracer, SafeTracer
from app.infrastructure.langsmith_tracer import LangSmithTracer
from app.infrastructure.providers import build_tracer
from tests.support.tracing import FailingTracer, RecordingTracer

CHUNK = RetrievedChunk(uuid.uuid4(), uuid.uuid4(), "sop.pdf", 2, None, "secret passage", 0.5)


class ExplodingSpan:
    def child(self, *args):
        raise RuntimeError("child boom")

    def end(self, *args):
        raise RuntimeError("end boom")


class ExplodingSpanTracer:
    def start(self, *args):
        return ExplodingSpan()


def test_safe_tracer_turns_start_failures_into_noop_and_logs_class(caplog) -> None:
    with caplog.at_level("WARNING", logger="app.tracing"):
        span = SafeTracer(FailingTracer()).start("chat", "chain", {}, {})
    assert isinstance(span, NoopSpan)
    [record] = [r for r in caplog.records if r.getMessage() == "trace_failed"]
    assert record.fields == {"action": "start", "error_class": "ConnectionError"}
    assert "backend down" not in caplog.text


def test_safe_span_swallows_child_and_end_failures() -> None:
    span = SafeTracer(ExplodingSpanTracer()).start("chat", "chain", {}, {})
    child = span.child("model", "llm", {})
    child.end({"x": 1})
    span.end(error="ValueError")  # must not raise


def test_default_payloads_are_metadata_only() -> None:
    payloads = TracePayloads()
    inputs = payloads.chat_inputs("What is confidential?", None, "auto")
    outputs = payloads.chat_outputs("answered", "Secret answer [S1].", ["S1"])
    retrieved = payloads.retrieved([CHUNK])
    sources = payloads.sources([Source("S1", CHUNK)], attempt=1)
    text = repr((inputs, outputs, retrieved, sources))
    assert "confidential" not in text and "Secret answer" not in text
    assert "secret passage" not in text
    assert inputs["question_chars"] == len("What is confidential?")
    assert retrieved["documents"][0]["chars"] == len("secret passage")
    assert sources["sources"][0]["label"] == "S1"


def test_content_is_traced_only_when_enabled() -> None:
    payloads = TracePayloads(include_content=True)
    assert payloads.chat_inputs("Q?", None, "qa")["question"] == "Q?"
    assert payloads.chat_outputs("answered", "A [S1]", ["S1"])["answer"] == "A [S1]"
    assert payloads.retrieved([CHUNK])["documents"][0]["text"] == "secret passage"


def test_tracer_factory_is_off_by_default_and_needs_a_key(monkeypatch) -> None:
    for name in ("TRACE_LANGSMITH", "TRACE_LANGSMITH_API_KEY", "LANGSMITH_TRACING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")  # standard var must not enable app tracing
    assert isinstance(build_tracer(Settings()), NoopTracer)
    assert isinstance(build_tracer(Settings(trace_langsmith=True)), NoopTracer)
    keyed = Settings(trace_langsmith=True, trace_langsmith_api_key=SecretStr("lsv2-test"))
    with patch("langsmith.Client") as client_class:
        tracer = build_tracer(keyed)
    assert isinstance(tracer, SafeTracer)
    assert client_class.call_args.kwargs["api_key"] == "lsv2-test"
    assert client_class.call_args.kwargs["omit_traced_runtime_info"] is True


def test_tracer_factory_falls_back_when_client_fails() -> None:
    keyed = Settings(trace_langsmith=True, trace_langsmith_api_key=SecretStr("lsv2-test"))
    with patch("langsmith.Client", side_effect=ValueError("bad endpoint")):
        assert isinstance(build_tracer(keyed), NoopTracer)


def test_langsmith_adapter_posts_and_patches_runs() -> None:
    client = MagicMock()
    with patch("app.infrastructure.langsmith_tracer.RunTree") as run_tree:
        root_run = run_tree.return_value
        child_run = root_run.create_child.return_value
        root = LangSmithTracer(client, "proj").start("chat", "chain", {"q": 1}, {"m": 2})
        child = root.child("model", "llm", {"attempt": 1})
        child.end({"output_chars": 10})
        root.end(error="ValueError")

    kwargs = run_tree.call_args.kwargs
    assert kwargs["project_name"] == "proj" and kwargs["ls_client"] is client
    assert kwargs["extra"] == {"metadata": {"m": 2}}
    assert kwargs["replicas"] == []
    root_run.post.assert_called_once()
    root_run.create_child.assert_called_once_with("model", "llm", inputs={"attempt": 1})
    child_run.post.assert_called_once()
    child_run.end.assert_called_once_with(outputs={"output_chars": 10}, error=None)
    root_run.end.assert_called_once_with(outputs=None, error="ValueError")
    root_run.patch.assert_called_once()


def test_recording_tracer_helper_records_tree() -> None:
    tracer = RecordingTracer()
    root = tracer.start("chat", "chain", {}, {})
    root.child("retrieve", "retriever", {}).end({"documents": []})
    root.end({"status": "answered"})
    assert [c.name for c in tracer.roots[0].children] == ["retrieve"]
