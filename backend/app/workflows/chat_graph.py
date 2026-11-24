"""LangGraph orchestration of one chat request.

    START -> route -> answer_qa ----------------------------> END
                   \\-> plan <-> act (bounded tool loop) -> synthesize -> END
                   \\-> END (route already produced an outcome)

Nodes are supplied by the application layer; this module owns only state, edges and the
hard step backstop. Request-scoped objects (deadline, trace span, scope) travel in the
LangGraph runtime context, not in graph state.
"""

import uuid
from dataclasses import dataclass, field
from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from app.application.answering import Citation
from app.domain.agent import ScopedDocument, ToolCall, ToolRecord
from app.domain.answers import AnswerStatus, Finding
from app.domain.deadline import Deadline
from app.domain.intent import Intent
from app.domain.providers import ChatMessage
from app.domain.retrieval import RetrievedChunk, Source
from app.domain.tracing import Span


@dataclass(frozen=True)
class ChatContext:
    question: str
    mode: str
    history: list[ChatMessage]
    # Explicit scope as requested (None = every ready document) and its resolved documents.
    document_ids: list[uuid.UUID] | None
    documents: list[ScopedDocument]
    deadline: Deadline
    root: Span


@dataclass(frozen=True)
class Outcome:
    status: AnswerStatus
    answer: str
    citations: list[Citation] = field(default_factory=list)
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


class ChatState(TypedDict, total=False):
    intent: Intent
    documents_listed: bool
    step: int
    searches: int
    rejected_streak: int
    log: list[ToolRecord]
    sources: list[Source]
    read: list[str]
    pending: ToolCall | None
    stop_reason: str | None
    outcome: Outcome


class ChatNodes(Protocol):
    def route(self, state: ChatState, context: ChatContext) -> dict: ...

    def answer_qa(self, state: ChatState, context: ChatContext) -> dict: ...

    def plan(self, state: ChatState, context: ChatContext) -> dict: ...

    def act(self, state: ChatState, context: ChatContext) -> dict: ...

    def synthesize(self, state: ChatState, context: ChatContext) -> dict: ...


def recursion_limit(max_steps: int) -> int:
    """Backstop above the agent's own step budget (plan + act per step, plus fixed nodes)."""
    return 2 * max_steps + 6


def _after_route(state: ChatState) -> str:
    if "outcome" in state:
        return END
    return "answer_qa" if state["intent"] == "qa" else "plan"


def _after_plan(state: ChatState) -> str:
    if state.get("stop_reason"):
        return "synthesize"
    return "act" if state.get("pending") else "plan"


def build_chat_graph(nodes: ChatNodes) -> CompiledStateGraph:
    def bind(method):
        def node(state: ChatState, runtime: Runtime[ChatContext]) -> dict:
            return method(state, runtime.context)

        return node

    graph = StateGraph(ChatState, context_schema=ChatContext)
    graph.add_node("route", bind(nodes.route))
    graph.add_node("answer_qa", bind(nodes.answer_qa))
    graph.add_node("plan", bind(nodes.plan))
    graph.add_node("act", bind(nodes.act))
    graph.add_node("synthesize", bind(nodes.synthesize))
    graph.add_edge(START, "route")
    graph.add_conditional_edges("route", _after_route, ["answer_qa", "plan", END])
    graph.add_conditional_edges("plan", _after_plan, ["act", "plan", "synthesize"])
    graph.add_edge("act", "plan")
    graph.add_edge("answer_qa", END)
    graph.add_edge("synthesize", END)
    return graph.compile(name="chat")
