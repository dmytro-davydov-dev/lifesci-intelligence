"""Comparison agent: the model selects read-only tools within step, search, context and
time budgets; evidence it gathers is then answered from with validated citations."""

import logging
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.application.agent_prompts import AGENT_SYSTEM_PROMPT, build_agent_prompt
from app.application.answering import AnswerGenerator, RequestTimeoutError, budget
from app.domain.agent import (
    AGENT_STEP_SCHEMA,
    AgentBudget,
    AgentStepError,
    ToolCall,
    ToolRecord,
    parse_step,
)
from app.domain.answers import INSUFFICIENT_EVIDENCE_MESSAGE
from app.domain.chunking import estimate_tokens
from app.domain.providers import ChatMessage, ChatProvider, EmbeddingProvider, ModelTimeoutError
from app.domain.retrieval import RetrievedChunk, Source
from app.workflows.chat_graph import ChatContext, ChatState, Outcome

logger = logging.getLogger("app.agent")

# Time kept back from planning and searching for the final answer (one call plus repair).
SYNTHESIS_RESERVE_SECONDS = 10.0
# Consecutive rejected steps before the loop gives up on planning.
MAX_REJECTED_STREAK = 2

Retriever = Callable[[Session, list[float], str, list[uuid.UUID] | None, int], list[RetrievedChunk]]


class ComparisonAgent:
    def __init__(
        self,
        session_factory: sessionmaker,
        embedder: EmbeddingProvider,
        chat: ChatProvider,
        retrieve: Retriever,
        generator: AnswerGenerator,
        agent_budget: AgentBudget,
        context_max_tokens: int,
    ) -> None:
        self._session_factory = session_factory
        self._embedder = embedder
        self._chat = chat
        self._retrieve = retrieve
        self._generator = generator
        self._budget = agent_budget
        self._context_max_tokens = context_max_tokens

    # -- plan: the model picks the next tool -------------------------------------------------

    def plan(self, state: ChatState, context: ChatContext) -> dict:
        step = state.get("step", 0) + 1
        if step > self._budget.max_steps:
            return _stop("step_budget")
        if context.deadline.remaining() < SYNTHESIS_RESERVE_SECONDS + 1.0:
            return _stop("deadline")

        sources = state.get("sources", [])
        documents = context.documents if state.get("documents_listed") else None
        prompt = build_agent_prompt(
            context.question,
            self._budget,
            step,
            state.get("searches", 0),
            documents,
            state.get("log", []),
            sources,
            set(state.get("read", [])),
        )
        messages = [
            ChatMessage("system", AGENT_SYSTEM_PROMPT),
            *context.history,
            ChatMessage("user", prompt),
        ]
        span = context.root.child("agent_step", "llm", {"step": step})
        try:
            raw = self._chat.complete_json(
                messages,
                "agent_step",
                AGENT_STEP_SCHEMA,
                timeout=budget(context.deadline, SYNTHESIS_RESERVE_SECONDS),
            )
        except (ModelTimeoutError, RequestTimeoutError) as exc:
            span.end(error=type(exc).__name__)
            logger.warning("agent_step_timeout step=%d", step)
            return {"step": step, **_stop("timeout")}
        except Exception as exc:
            span.end(error=type(exc).__name__)
            raise

        try:
            call = parse_step(
                raw,
                documents={d.label for d in documents or []},
                sources={s.label for s in sources},
                searches_left=self._budget.max_searches - state.get("searches", 0),
            )
        except AgentStepError as error:
            span.end({"rejected": error.code})
            logger.warning("agent_step_rejected step=%d code=%s", step, error.code)
            streak = state.get("rejected_streak", 0) + 1
            update: dict = {
                "step": step,
                "pending": None,
                "rejected_streak": streak,
                "log": [*state.get("log", []), ToolRecord(step, None, f"rejected: {error}")],
            }
            if streak >= MAX_REJECTED_STREAK:
                update["stop_reason"] = "invalid_steps"
            return update

        span.end({"action": call.action, "document": call.document})
        if call.action == "finish":
            return {"step": step, "rejected_streak": 0, **_stop("finished")}
        return {"step": step, "pending": call, "rejected_streak": 0}

    # -- act: run the validated read-only tool -----------------------------------------------

    def act(self, state: ChatState, context: ChatContext) -> dict:
        call: ToolCall = state["pending"]  # type: ignore[assignment]
        step = state["step"]
        span = context.root.child(
            "tool", "tool", {"action": call.action, "document": call.document}
        )
        update: dict = {"pending": None}
        if call.action == "list_documents":
            update["documents_listed"] = True
            outcome = f"{len(context.documents)} documents"
        elif call.action == "read_passage":
            update["read"] = sorted({*state.get("read", []), call.source or ""})
            outcome = "full text shown in SOURCES FOUND"
        else:
            update["searches"] = state.get("searches", 0) + 1
            try:
                sources, outcome = self._search(call, state.get("sources", []), context)
            except (ModelTimeoutError, RequestTimeoutError) as exc:
                span.end(error=type(exc).__name__)
                logger.warning("agent_search_timeout step=%d", step)
                record = ToolRecord(step, call, "failed: timed out")
                return {**update, "log": [*state.get("log", []), record], **_stop("timeout")}
            except Exception as exc:
                span.end(error=type(exc).__name__)
                raise
            update["sources"] = sources
        span.end({"outcome": outcome if call.action != "search" else "searched"})
        update["log"] = [*state.get("log", []), ToolRecord(step, call, outcome)]
        return update

    def _search(
        self, call: ToolCall, sources: list[Source], context: ChatContext
    ) -> tuple[list[Source], str]:
        if call.document is not None:
            labels = {d.label: d.document_id for d in context.documents}
            scope: list[uuid.UUID] | None = [labels[call.document]]
        else:
            scope = context.document_ids
        query = call.query or ""
        vector = self._embedder.embed(
            [query], timeout=budget(context.deadline, SYNTHESIS_RESERVE_SECONDS)
        )[0]
        with self._session_factory() as session:
            found = self._retrieve(session, vector, query, scope, self._budget.results_per_search)

        known = {source.chunk.chunk_id: source.label for source in sources}
        used = sum(estimate_tokens(source.chunk.text) for source in sources)
        new, seen, skipped = [], [], 0
        ledger = list(sources)
        for chunk in found:
            if chunk.chunk_id in known:
                seen.append(known[chunk.chunk_id])
                continue
            cost = estimate_tokens(chunk.text)
            if used + cost > self._context_max_tokens:
                skipped += 1
                continue
            used += cost
            label = f"S{len(ledger) + 1}"
            ledger.append(Source(label, chunk))
            known[chunk.chunk_id] = label
            new.append(label)

        parts = []
        if new:
            parts.append(", ".join(new) + " (new)")
        if seen:
            parts.append(", ".join(seen) + " (already found)")
        if skipped:
            parts.append(f"{skipped} not added: context budget full")
        return ledger, "; ".join(parts) or "no matching passages"

    # -- synthesize: grounded answer from the gathered evidence ------------------------------

    def synthesize(self, state: ChatState, context: ChatContext) -> dict:
        sources = state.get("sources", [])
        logger.info(
            "agent_finished",
            extra={
                "fields": {
                    "stop_reason": state.get("stop_reason"),
                    "steps": state.get("step", 0),
                    "searches": state.get("searches", 0),
                    "sources": len(sources),
                }
            },
        )
        retrieved = [source.chunk for source in sources]
        if not sources:
            return {"outcome": Outcome("insufficient_evidence", INSUFFICIENT_EVIDENCE_MESSAGE)}
        status, answer, citations = self._generator.generate(
            context.question, context.history, sources, context.deadline, context.root
        )
        return {"outcome": Outcome(status, answer, citations, retrieved)}


def _stop(reason: str) -> dict:
    return {"pending": None, "stop_reason": reason}
