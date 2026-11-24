# ADR 0007: Structured logs and optional LangSmith tracing

Status: accepted (T13, 2026-11-24)

## Decisions
- **Structured logs:** `app.*` loggers emit JSON lines (`ts`, `level`, `logger`, `event`, `request_id` + event fields) to stderr. A context variable set by the request middleware carries the request id into handlers and threadpool code.
  - Events: `request_completed` (method, path, status, duration), `chat_completed` (status, intent, retrieval mode, retrieved/citation/history counts, agent steps, duration), `agent_finished` (stop reason, steps, searches, sources), `model_usage` (model, prompt/completion/total tokens), `document_ingested`, validation/deadline/injection warnings (reason codes and counts), `trace_failed`.
  - Exceptions log the error class only. Uvicorn's access log is disabled to keep a single structured stream.
- **What is never logged:** document text, questions, answers, provider error messages and secrets.
- **Tracing interface:** `Tracer`/`Span` in the domain layer, with a no-op default. `ChatService` traces a `chat` root with `retrieve` and per-attempt `model` children, and records the error class on failure.
- **LangSmith (optional):** `langsmith==0.14.17`, pinned as the latest release at least two weeks old. Only prebuilt wheels are installed; there are no build scripts.
  - Enabled only with `TRACE_LANGSMITH=true` and `TRACE_LANGSMITH_API_KEY`. These are app-specific names on purpose: the standard `LANGSMITH_TRACING`/`LANGSMITH_API_KEY` also switch on LangChain/LangGraph auto-tracing of full prompts and outputs, which would bypass the redaction policy. Never set the standard variables. Without a key, or if the client fails to construct, tracing falls back to no-op with a warning.
  - Runs use an explicit `Client` and `RunTree`, with no global auto-tracing. `replicas=[]` stops mirroring to `LANGSMITH_RUNS_ENDPOINTS`, and `omit_traced_runtime_info=True` stops sending platform/git metadata. Every tracer injected into `ChatService` is wrapped in `SafeTracer`. Test fixtures force tracing off whatever the shell environment says.
- **Redaction policy:** trace payloads hold only metadata by default: lengths, counts, chunk/document ids, labels, pages, scores, statuses and error class names. `TRACE_INCLUDE_CONTENT=true` adds question, answer and source text. Enable it only for approved public or synthetic fixtures.
- **Failure isolation:** `SafeTracer`/`SafeSpan` catch every tracing exception, log `trace_failed` with action and error class, and continue with no-op spans. LangSmith upload errors arrive through `tracing_error_callback` and are logged the same way. Client timeouts are 2 s connect / 5 s read, and uploads are batched in the background. Tests use an in-memory tracer and never touch the network.

## Known limitations
- The langsmith SDK's own loggers and uvicorn's error logger are not JSON-formatted. SDK upload failures may print the API URL, but no secrets.
- Request durations stop when response headers are sent, so streamed bodies (`/file`) are excluded.
- The SDK's background upload thread may delay shutdown by up to the 5 s upload timeout while the queue flushes.
- Traces don't carry the request id yet, so a trace can't be matched to its log lines.
- No live LangSmith run has been executed: there is no key in this environment. The adapter is verified against the library API with a mocked `RunTree`.
- Token usage is logged but not yet aggregated into eval reports. Cost is not computed.
- Ingestion and the eval runner are not traced. Spans are not linked to LangSmith datasets or experiments.
