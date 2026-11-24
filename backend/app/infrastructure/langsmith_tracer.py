"""LangSmith tracing adapter (optional; disabled by default)."""

from typing import Any

from langsmith import Client
from langsmith.run_trees import RunTree

from app.domain.tracing import RunType


class LangSmithSpan:
    def __init__(self, run: RunTree) -> None:
        self._run = run

    def child(self, name: str, run_type: RunType, inputs: dict[str, Any]) -> "LangSmithSpan":
        child = self._run.create_child(name, run_type, inputs=inputs)
        child.post()
        return LangSmithSpan(child)

    def end(self, outputs: dict[str, Any] | None = None, error: str | None = None) -> None:
        self._run.end(outputs=outputs, error=error)
        self._run.patch()


class LangSmithTracer:
    def __init__(self, client: Client, project: str) -> None:
        self._client = client
        self._project = project

    def start(
        self, name: str, run_type: RunType, inputs: dict[str, Any], metadata: dict[str, Any]
    ) -> LangSmithSpan:
        run = RunTree(
            name=name,
            run_type=run_type,
            inputs=inputs,
            project_name=self._project,
            ls_client=self._client,
            extra={"metadata": metadata},
            replicas=[],  # never mirror to endpoints from LANGSMITH_RUNS_ENDPOINTS
        )
        run.post()
        return LangSmithSpan(run)
