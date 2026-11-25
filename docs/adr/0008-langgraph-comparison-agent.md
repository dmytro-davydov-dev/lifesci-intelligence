# ADR 0008: LangGraph orchestration and the bounded comparison agent

Status: accepted (T14–T15, 2026-11-24)

## Decisions
- **Dependency:** `langgraph==1.2.20`, the newest release at least two weeks old. It adds 10 locked packages: langchain-core, the langgraph checkpoint/prebuilt/sdk packages, langchain-protocol, jsonpatch, jsonpointer, ormsgpack and tenacity. All install from prebuilt wheels. No checkpointer, store or LangGraph server is used.
- **Graph:** `app/workflows/chat_graph.py` owns state, edges and a recursion backstop: `route -> answer_qa | plan <-> act -> synthesize`. The application layer (`ChatService`, `ComparisonAgent`) supplies the nodes. Request-scoped objects travel in the LangGraph runtime context, not in graph state: the deadline, trace span, history and resolved scope.
- **Intent routing is a rule, not a model call** (`app/domain/intent.py`). `mode=qa|compare` is honoured. `auto` picks compare only for comparison wording ("compare", "align", "gap", "versus", "what changed"...) with at least two ready documents in scope. "difference" is deliberately not a trigger, after review: definition questions such as "the difference between minor and major deviations" are single-document Q&A, and the two-document findings contract would make them abstain. Explicit compare with fewer than two documents returns `clarification` without any model call. The rule is cheap and reproducible. All 16 golden questions route as their category expects (unit-tested).
- **Model-selected read-only tools:** each planning step is one strict structured-output call (`agent_step` schema: `action`, `query`, `document`, `source`). The tools:
  - `list_documents`: in-scope ready documents, labelled D1.. by name.
  - `search`: the configured vector/hybrid retrieval, restricted to one D label or the whole request scope.
  - `read_passage`: full text of a found S label. Search results show 300-character snippets until a passage is read.
  - `finish`.

  The prompt is rebuilt from validated state every step, so it is bounded and is not an open transcript. Arguments are checked against allowlists (D labels from the resolved scope, S labels from the evidence ledger), and queries are truncated to 200 characters. Full-text search already strips tsquery operators. There are no shell, web, write or generated-SQL tools.
- **Budgets:** `AGENT_MAX_STEPS=6`, `AGENT_MAX_SEARCHES=3` (the plan's three retrieval rounds), `AGENT_RESULTS_PER_SEARCH=4`. The evidence ledger is capped at `CONTEXT_MAX_TOKENS`. Planning and searches keep 10 s of the 45 s request deadline for the final answer.
  - Running out of steps, nearing the deadline, a planning or search timeout, a provider error once some evidence exists, or two consecutive rejected steps all stop planning. The answer is then built from the evidence gathered so far.
  - A provider error before any evidence exists still returns 503. A search without a D label covers exactly the documents listed to the model, resolved once per request.
  - With no evidence, the response is `insufficient_evidence` without an answer call. LangGraph's recursion limit is a backstop above the step budget.
- **Answering:** the gathered sources go through the same generator as Q&A (`app/application/answering.py`) under the comparison contract below. That means the same allowlisted citation labels, database-derived quotes, injection echo checks, one repair attempt, and abstention.
- **Structured findings (T15):** comparison synthesis uses a separate strict schema (`comparison_findings`): `status`, `answer`, `citation_ids`, and `findings[]` of `{topic, assessment, explanation, citation_ids}`. `assessment` is one of `supported`, `potential_gap` or `insufficient_evidence`; there is deliberately no "compliant" value.
  - Validation (`app/domain/findings.py`) runs the Q&A answer rules first. Then every finding needs a topic and an explanation, at most 8 findings are allowed, and finding citations (ids and inline markers) must be allowlisted labels.
  - A `supported` or `potential_gap` finding must cite at least two different documents, so a one-sided reading is never presented as a comparison. It should fall back to `insufficient_evidence`.
  - The response's citations are the union of answer and finding labels, with quotes and pages taken from the database. The injection echo and prompt-leak checks also cover finding topics and explanations, and topics may not carry citation markers.
  - Any violation gets one repair attempt, then the request abstains. The QA and comparison contracts share one generator.
- **API/UI:** `POST /api/chat` returns `findings` (empty for Q&A). The chat panel shows each finding with an assessment badge, and its `[S#]` markers open the evidence panel. A note states that potential gaps are for human review, not a compliance determination. Findings are not persisted with the conversation; history replays only the answer text.
- **No accidental telemetry:** with `LANGSMITH_TRACING=true` set, an unguarded graph run was verified to construct LangChain's tracer and POST full runs. `ChatService` therefore runs the graph inside `langsmith.tracing_context(enabled=False)`. Only the redacting app tracer emits spans (`agent_step`, `tool`, `model`), and they carry metadata only. An integration test asserts no LangChain tracer is created.
- **Offline behaviour:** the fake `ExtractiveChatProvider` follows a fixed policy so tests and keyless demos exercise the real loop. It lists documents, searches the documents whose names share the most tokens with the question, then finishes. Its single finding is always `insufficient_evidence`, quoting the best passage of each document. This is not model judgement.

## Known limitations
- Routing by wording can miss implicit comparisons ("Is SOP-002 sufficient against the reference?"). Users can force `mode=compare`.
- Planning calls add latency and tokens: up to 6 extra calls.
- Tool steps and findings are not persisted. Only the final answer and citations are stored, so a reloaded conversation shows no findings.
- Database retrieval inside a search has no statement timeout. A slow query can eat into the time reserved for the answer, which then returns 504 if less than 1 s remains.
- Conversation history (bounded to 6 messages) is resent on every planning call. It helps with follow-ups ("compare those") but costs tokens.
