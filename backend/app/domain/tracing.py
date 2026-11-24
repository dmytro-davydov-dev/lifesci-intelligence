"""Tracing interface. Implementations must never let tracing failures reach callers."""

import logging
from typing import Any, Literal, Protocol

RunType = Literal["chain", "retriever", "llm", "embedding", "tool"]

logger = logging.getLogger("app.tracing")


class Span(Protocol):
    def child(self, name: str, run_type: RunType, inputs: dict[str, Any]) -> "Span": ...

    def end(self, outputs: dict[str, Any] | None = None, error: str | None = None) -> None: ...


class Tracer(Protocol):
    def start(
        self, name: str, run_type: RunType, inputs: dict[str, Any], metadata: dict[str, Any]
    ) -> Span: ...


class NoopSpan:
    def child(self, name: str, run_type: RunType, inputs: dict[str, Any]) -> "NoopSpan":
        return self

    def end(self, outputs: dict[str, Any] | None = None, error: str | None = None) -> None:
        return None


class NoopTracer:
    def start(
        self, name: str, run_type: RunType, inputs: dict[str, Any], metadata: dict[str, Any]
    ) -> NoopSpan:
        return NoopSpan()


def _report(action: str, exc: Exception) -> None:
    logger.warning(
        "trace_failed", extra={"fields": {"action": action, "error_class": type(exc).__name__}}
    )


class SafeSpan:
    def __init__(self, inner: Span) -> None:
        self._inner = inner

    def child(self, name: str, run_type: RunType, inputs: dict[str, Any]) -> Span:
        try:
            return SafeSpan(self._inner.child(name, run_type, inputs))
        except Exception as exc:
            _report("child", exc)
            return NoopSpan()

    def end(self, outputs: dict[str, Any] | None = None, error: str | None = None) -> None:
        try:
            self._inner.end(outputs, error)
        except Exception as exc:
            _report("end", exc)


class SafeTracer:
    """Isolates tracing failures: errors are logged by class and replaced by no-op spans."""

    def __init__(self, inner: Tracer) -> None:
        self._inner = inner

    def start(
        self, name: str, run_type: RunType, inputs: dict[str, Any], metadata: dict[str, Any]
    ) -> Span:
        try:
            return SafeSpan(self._inner.start(name, run_type, inputs, metadata))
        except Exception as exc:
            _report("start", exc)
            return NoopSpan()
