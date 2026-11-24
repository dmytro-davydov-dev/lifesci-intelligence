"""In-memory tracer for tests."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RecordedSpan:
    name: str
    run_type: str
    inputs: dict[str, Any]
    children: list["RecordedSpan"] = field(default_factory=list)
    outputs: dict[str, Any] | None = None
    error: str | None = None
    ended: bool = False

    def child(self, name: str, run_type: str, inputs: dict[str, Any]) -> "RecordedSpan":
        span = RecordedSpan(name, run_type, inputs)
        self.children.append(span)
        return span

    def end(self, outputs: dict[str, Any] | None = None, error: str | None = None) -> None:
        self.outputs, self.error, self.ended = outputs, error, True


class RecordingTracer:
    def __init__(self) -> None:
        self.roots: list[RecordedSpan] = []

    def start(self, name, run_type, inputs, metadata) -> RecordedSpan:
        span = RecordedSpan(name, run_type, {**inputs, "_metadata": metadata})
        self.roots.append(span)
        return span


class FailingTracer:
    def start(self, *args, **kwargs):
        raise ConnectionError("tracing backend down")
