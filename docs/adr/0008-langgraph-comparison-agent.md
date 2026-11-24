# ADR 0008: LangGraph orchestration and the bounded comparison agent

Status: accepted (T14, 2026-11-24)

## Decisions
- **Dependency:** `langgraph==1.2.20`, the newest release at least two weeks old. It adds 10 locked packages: langchain-core, the langgraph checkpoint/prebuilt/sdk packages, langchain-protocol, jsonpatch, jsonpointer, ormsgpack and tenacity. All install from prebuilt wheels. No checkpointer, store or LangGraph server is used.
- **Graph:** `app/workflows/chat_graph.py` owns state, edges and a recursion backstop: `route -> answer_qa | plan <-> act -> synthesize`. The application layer (`ChatService`, `ComparisonAgent`) supplies the nodes. Request-scoped objects travel in the LangGraph runtime context, not in graph state: the deadline, trace span, history and resolved scope.
- **Intent routing is a rule, not a model call** (`app/domain/intent.py`). `mode=qa|compare` is honoured. `auto` picks compare only for comparison wording ("compare", "align", "gap", "versus", "what changed"...) with at least two ready documents in scope. Explicit compare with fewer than two documents returns `clarification` without any model call. The rule is cheap and reproducible. All 16 golden questions route as their category expects (unit-tested).
- **Model-selected read-only tools:** each planning step is one strict structured-output call (`agent_step` schema: `action`, `query`, `document`, `source`). The tools:
  - `list_documents`: in-scope ready documents, labelled D1.. by name.
  - `search`: the configured vector/hybrid retrieval, restricted to one D label or the whole request scope.
  - `read_passage`: full text of a found S label. Search results show 300-character snippets until a passage is read.
  - `finish`.

  The prompt is rebuilt from validated state every step, so it is bounded and is not an open transcript. Arguments are checked against allowlists (D labels from the resolved scope, S labels from the evidence ledger), and queries are truncated to 200 characters. Full-text search already strips tsquery operators. There are no shell, web, write or generated-SQL tools.
- **Budgets:** `AGENT_MAX_STEPS=6`, `AGENT_MAX_SEARCHES=3` (the plan's three retrieval rounds), `AGENT_RESULTS_PER_SEARCH=4`. The evidence ledger is capped at `CONTEXT_MAX_TOKENS`. Planning and searches keep 10 s of the 45 s request deadline for the final answer.
  - Running out of steps, nearing the deadline, a planning or search timeout, or two consecutive rejected steps all stop planning, and the answer is built from the evidence gathered so far.
  - With no evidence, the response is `insufficient_evidence` without an answer call. LangGraph's recursion limit is a backstop above the step budget.
- **Answering:** the gathered sources go through the same grounded-answer generator as Q&A (`app/application/answering.py`). That means the same allowlisted citation labels, database-derived quotes, injection echo checks, one repair attempt, and abstention.
- **No accidental telemetry:** with `LANGSMITH_TRACING=true` set, an unguarded graph run was verified to construct LangChain's tracer and POST full runs. `ChatService` therefore runs the graph inside `langsmith.tracing_context(enabled=False)`. Only the redacting app tracer emits spans (`agent_step`, `tool`, `model`), and they carry metadata only. An integration test asserts no LangChain tracer is created.
- **Offline behaviour:** the fake `ExtractiveChatProvider` follows a fixed policy so tests and keyless demos exercise the real loop. It lists documents, searches the documents whose names share the most tokens with the question, then finishes. This is not model judgement.

## Known limitations
- Routing by wording can miss implicit comparisons ("Is SOP-002 sufficient against the reference?"). Users can force `mode=compare`.
- Planning calls add latency and tokens: up to 6 extra calls. No live-model run has been executed, because there is no API key in this environment.
- Tool steps are not persisted; only the final answer and citations are stored with the conversation.
