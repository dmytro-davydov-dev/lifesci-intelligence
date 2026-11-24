"""Chat use case: intent routing between grounded Q&A and the comparison agent."""

import logging
import time
import uuid
from dataclasses import dataclass, field, fields
from typing import Literal

from langgraph.errors import GraphRecursionError
from langsmith import tracing_context
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.application.answering import (
    AnswerGenerator,
    Citation,
    RequestTimeoutError,
    budget,
)
from app.application.comparison import ComparisonAgent
from app.application.prompts import history_content
from app.application.trace_payloads import TracePayloads
from app.config import Settings
from app.domain.agent import AgentBudget, ScopedDocument
from app.domain.answers import (
    INSUFFICIENT_EVIDENCE_MESSAGE,
    AnswerStatus,
    Finding,
    strip_markers,
)
from app.domain.deadline import Clock, Deadline
from app.domain.intent import MIN_COMPARE_DOCUMENTS, route_intent
from app.domain.providers import ChatMessage, ChatProvider, EmbeddingProvider
from app.domain.retrieval import RetrievedChunk, select_sources
from app.domain.tracing import NoopTracer, SafeTracer, Span, Tracer
from app.infrastructure.conversation_repository import ConversationRepository
from app.infrastructure.models import Document
from app.infrastructure.retrieval import hybrid_search, vector_search
from app.workflows.chat_graph import (
    ChatContext,
    ChatState,
    Outcome,
    build_chat_graph,
    recursion_limit,
)

__all__ = [
    "ChatResult",
    "ChatService",
    "ChatSettings",
    "Citation",
    "ConversationNotFoundError",
    "InvalidDocumentScopeError",
    "RequestTimeoutError",
]

logger = logging.getLogger("app.chat")

Mode = Literal["auto", "qa", "compare"]
RetrievalMode = Literal["vector", "hybrid"]
COMPARE_NEEDS_DOCUMENTS_MESSAGE = (
    "A comparison needs at least two ready documents in scope. Select the documents to compare."
)


class ConversationNotFoundError(Exception):
    pass


class InvalidDocumentScopeError(Exception):
    pass


@dataclass(frozen=True)
class ChatResult:
    conversation_id: uuid.UUID
    status: AnswerStatus
    answer: str
    citations: list[Citation] = field(default_factory=list)
    # Ranked chunks the answer drew on (for evaluation; not exposed by the API).
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    intent: str = "qa"
    findings: list[Finding] = field(default_factory=list)
    agent_steps: int = 0


@dataclass(frozen=True)
class ChatSettings:
    top_k: int = 8
    retrieval_mode: RetrievalMode = "hybrid"
    candidate_pool: int = 20
    rrf_k: int = 60
    context_max_tokens: int = 6000
    history_max_messages: int = 6
    history_message_max_chars: int = 2000
    request_deadline_seconds: float = 45.0
    agent_max_steps: int = 6
    agent_max_searches: int = 3
    agent_results_per_search: int = 4

    @classmethod
    def from_settings(cls, settings: Settings, **overrides) -> "ChatSettings":
        names = {f.name for f in fields(cls)}
        values = {
            "top_k": settings.retrieval_top_k,
            "retrieval_mode": settings.retrieval_mode,
            "candidate_pool": settings.retrieval_candidate_pool,
            "rrf_k": settings.rrf_k,
            **{name: getattr(settings, name) for name in names if hasattr(settings, name)},
        }
        return cls(**{**values, **overrides})


class ChatService:
    def __init__(
        self,
        session_factory: sessionmaker,
        embedder: EmbeddingProvider,
        chat: ChatProvider,
        settings: ChatSettings | None = None,
        clock: Clock = time.monotonic,
        tracer: Tracer | None = None,
        trace_payloads: TracePayloads | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._embedder = embedder
        self._settings = settings or ChatSettings()
        self._clock = clock
        self._tracer: Tracer = SafeTracer(tracer) if tracer else NoopTracer()
        self._payloads = trace_payloads or TracePayloads()
        self._generator = AnswerGenerator(chat, self._payloads)
        self._agent_budget = AgentBudget(
            max_steps=self._settings.agent_max_steps,
            max_searches=self._settings.agent_max_searches,
            results_per_search=self._settings.agent_results_per_search,
        )
        self._agent = ComparisonAgent(
            session_factory,
            embedder,
            chat,
            self._retrieve,
            self._generator,
            self._agent_budget,
            self._settings.context_max_tokens,
        )
        self._graph = build_chat_graph(self)

    def ask(
        self,
        question: str,
        conversation_id: uuid.UUID | None = None,
        document_ids: list[uuid.UUID] | None = None,
        mode: Mode = "auto",
    ) -> ChatResult:
        root = self._tracer.start(
            "chat",
            "chain",
            self._payloads.chat_inputs(question.strip(), document_ids, mode),
            {"retrieval_mode": self._settings.retrieval_mode, "top_k": self._settings.top_k},
        )
        try:
            result = self._ask(question, conversation_id, document_ids, mode, root)
        except Exception as exc:
            root.end(error=type(exc).__name__)
            raise
        root.end(
            {
                **self._payloads.chat_outputs(
                    result.status, result.answer, [c.label for c in result.citations]
                ),
                "intent": result.intent,
            }
        )
        return result

    def _ask(
        self,
        question: str,
        conversation_id: uuid.UUID | None,
        document_ids: list[uuid.UUID] | None,
        mode: Mode,
        root: Span,
    ) -> ChatResult:
        question = question.strip()
        started = self._clock()
        deadline = Deadline(self._settings.request_deadline_seconds, self._clock)

        with self._session_factory() as session:
            conversations = ConversationRepository(session)
            if conversation_id is not None and not conversations.exists(conversation_id):
                raise ConversationNotFoundError(str(conversation_id))
            documents = self._scope_documents(session, document_ids)
            history = (
                conversations.recent_messages(conversation_id, self._settings.history_max_messages)
                if conversation_id
                else []
            )
            # Earlier labels (S1..) are reassigned every turn; strip them so the model
            # cannot reuse a stale label for an unrelated current source.
            limit = self._settings.history_message_max_chars
            history_messages = [
                ChatMessage(
                    m.role,
                    history_content(
                        strip_markers(m.content) if m.role == "assistant" else m.content, limit
                    ),
                )
                for m in history
            ]

        context = ChatContext(
            question=question,
            mode=mode,
            history=history_messages,
            document_ids=document_ids,
            documents=documents,
            deadline=deadline,
            root=root,
        )
        state = self._run_graph(context)
        outcome: Outcome = state["outcome"]
        intent = state.get("intent", "qa")

        logger.info(
            "chat_completed",
            extra={
                "fields": {
                    "status": outcome.status,
                    "intent": intent,
                    "retrieval_mode": self._settings.retrieval_mode,
                    "retrieved": len(outcome.retrieved),
                    "citations": len(outcome.citations),
                    "agent_steps": state.get("step", 0),
                    "history_messages": len(history_messages),
                    "duration_ms": round((self._clock() - started) * 1000, 1),
                }
            },
        )
        with self._session_factory.begin() as session:
            conversations = ConversationRepository(session)
            if conversation_id is None:
                conversation_id = conversations.create().id
            conversations.add_message(conversation_id, "user", question)
            conversations.add_message(
                conversation_id,
                "assistant",
                outcome.answer,
                [c.to_json() for c in outcome.citations],
            )
        return ChatResult(
            conversation_id,
            outcome.status,
            outcome.answer,
            outcome.citations,
            outcome.retrieved,
            intent,
            outcome.findings,
            state.get("step", 0),
        )

    def _run_graph(self, context: ChatContext) -> ChatState:
        # LangChain/LangGraph auto-tracing is forced off: only the redacting app tracer
        # may emit traces, whatever LANGSMITH_* variables are set in the environment.
        with tracing_context(enabled=False):
            try:
                return self._graph.invoke(
                    {},
                    context=context,
                    config={"recursion_limit": recursion_limit(self._agent_budget.max_steps)},
                )
            except GraphRecursionError:
                # Unreachable while the agent enforces its own step budget; abstain if not.
                logger.error("agent_recursion_limit")
                return {"outcome": Outcome("insufficient_evidence", INSUFFICIENT_EVIDENCE_MESSAGE)}

    # -- graph nodes -------------------------------------------------------------------------

    def route(self, state: ChatState, context: ChatContext) -> dict:
        intent = route_intent(context.question, context.mode, len(context.documents))
        if intent == "compare" and len(context.documents) < MIN_COMPARE_DOCUMENTS:
            return {
                "intent": intent,
                "outcome": Outcome("clarification", COMPARE_NEEDS_DOCUMENTS_MESSAGE),
            }
        return {"intent": intent}

    def answer_qa(self, state: ChatState, context: ChatContext) -> dict:
        question = context.question
        query_vector = self._embedder.embed([question], timeout=budget(context.deadline))[0]
        retrieval = context.root.child(
            "retrieve", "retriever", {"mode": self._settings.retrieval_mode}
        )
        try:
            with self._session_factory() as session:
                chunks = self._retrieve(
                    session, query_vector, question, context.document_ids, self._settings.top_k
                )
        except Exception as exc:
            retrieval.end(error=type(exc).__name__)
            raise
        retrieval.end(self._payloads.retrieved(chunks))

        sources = select_sources(chunks, self._settings.context_max_tokens)
        if not sources:
            return {"outcome": Outcome("insufficient_evidence", INSUFFICIENT_EVIDENCE_MESSAGE)}
        generated = self._generator.generate(
            question, context.history, sources, context.deadline, context.root
        )
        return {"outcome": Outcome(generated.status, generated.answer, generated.citations, chunks)}

    def plan(self, state: ChatState, context: ChatContext) -> dict:
        return self._agent.plan(state, context)

    def act(self, state: ChatState, context: ChatContext) -> dict:
        return self._agent.act(state, context)

    def synthesize(self, state: ChatState, context: ChatContext) -> dict:
        return self._agent.synthesize(state, context)

    # -- helpers -----------------------------------------------------------------------------

    def _retrieve(
        self,
        session: Session,
        query_vector: list[float],
        query: str,
        document_ids: list[uuid.UUID] | None,
        top_k: int,
    ) -> list[RetrievedChunk]:
        settings = self._settings
        if settings.retrieval_mode == "vector":
            return vector_search(session, query_vector, document_ids, top_k)
        return hybrid_search(
            session,
            query_vector,
            query,
            document_ids,
            top_k,
            candidate_pool=max(settings.candidate_pool, top_k),
            rrf_k=settings.rrf_k,
        )

    def _scope_documents(
        self, session: Session, document_ids: list[uuid.UUID] | None
    ) -> list[ScopedDocument]:
        """Ready documents in scope, labelled D1.. by name. Explicit ids must all be ready."""
        statement = select(Document.id, Document.name, Document.version).where(
            Document.status == "ready"
        )
        if document_ids is not None:
            if not document_ids:
                raise InvalidDocumentScopeError(
                    "document_ids must not be empty; omit it to use all."
                )
            statement = statement.where(Document.id.in_(document_ids))
        rows = session.execute(statement.order_by(Document.name, Document.id)).all()
        if document_ids is not None:
            ready = {row.id for row in rows}
            if missing := [str(d) for d in document_ids if d not in ready]:
                raise InvalidDocumentScopeError(
                    "Unknown or not-ready document ids: " + ", ".join(sorted(set(missing)))
                )
        return [
            ScopedDocument(f"D{index}", row.id, row.name, row.version)
            for index, row in enumerate(rows, start=1)
        ]
