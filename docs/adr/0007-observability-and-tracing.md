# ADR 0007: Structured logs and optional LangSmith tracing

Status: accepted (T13, 2026-11-24)

## Decisions
- **Structured logs:** `app.*` loggers emit JSON lines (`ts`, `level`, `logger`, `event`, `request_id` + event fields) to stderr. A context variable set by the request middleware carries the request id into handlers and threadpool code.
  - Events: `request_completed` (method, path, status, duration), `chat_completed` (status, retrieval mode, retrieved/source/citation/history counts, duration), `model_usage` (model, prompt/completion/total tokens), `document_ingested`, validation/deadline/injection warnings (reason codes and counts), `trace_failed`.
  - Exceptions log the error class only. Uvicorn's access log is disabled to keep a single structured stream.
- **What is never logged:** document text, questions, answers, provider error messages and secrets.
- **Tracing interface:** `Tracer`/`Span` in the domain layer, with a no-op default. `ChatService` traces a `chat` root with `retrieve` and per-attempt `model` children, and records the error class on failure.
- **LangSmith (optional):** `langsmith==0.14.17`, pinned as the latest release at least two weeks old. Only prebuilt wheels are installed; there are no build scripts.
  - Enabled only with `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`. Without a key, or if the client fails to construct, tracing falls back to no-op with a warning.
  - Runs use an explicit `Client` and `RunTree`, with no global auto-tracing.
- **Redaction policy:** trace payloads hold only metadata by default: lengths, counts, chunk/document ids, labels, pages, scores, statuses and error class names. `TRACE_INCLUDE_CONTENT=true` adds question, answer and source text. Enable it only for approved public or synthetic fixtures.
- **Failure isolation:** `SafeTracer`/`SafeSpan` catch every tracing exception, log `trace_failed` with action and error class, and continue with no-op spans. LangSmith upload errors arrive through `tracing_error_callback` and are logged the same way. Client timeouts are 2 s connect / 5 s read, and uploads are batched in the background. Tests use an in-memory tracer and never touch the network.

## Known limitations
- No live LangSmith run has been executed: there is no key in this environment. The adapter is verified against the library API with a mocked `RunTree`.
- Token usage is logged but not yet aggregated into eval reports. Cost is not computed.
- Ingestion and the eval runner are not traced. Spans are not linked to LangSmith datasets or experiments.
