# ADR 0003: Grounded answers, citation validation and abstention

Status: accepted (T06, 2026-11-24)

## Decisions
- **Retrieval:** exact cosine search (pgvector, no index), top 8, `ready` documents only, optional server-validated `document_ids` scope (unknown, not-ready or empty lists are rejected with 422).
- **Context:** chunks are added in rank order until a ~6000-token budget (chars/4) is spent and exposed as `S1..Sn`. Each is fenced in `<source>` tags with tag-like text escaped; the system prompt marks sources as untrusted data and history as non-evidence.
- **Structured output:** the model returns `{status, answer, citation_ids}` via strict JSON schema. Citation ids, including inline `[S#]` markers, must be in the allowlist; `answered` needs at least one. Quotes, pages, sections and document names come from the database, never from the model. Invalid output gets one repair prompt; a second failure abstains (`insufficient_evidence`).
- **Abstention without a model call** when nothing is retrieved. No similarity threshold yet; it will be tuned with evals (T11/T12).
- **Provider errors** return `503 model_unavailable` and persist nothing; abstention is reserved for lack of evidence.
- **History:** last 6 messages are sent as context. Messages get an identity `seq` column because `created_at` (`now()`) ties within a transaction.
- **Chat model:** `OPENAI_CHAT_MODEL` has no default and is required when `MODEL_PROVIDER=openai`. The offline default is an extractive stand-in that quotes the source with the most shared terms or abstains; it is deterministic test/demo scaffolding, not a model.
- **`mode=compare`** returns `422 mode_unavailable` until T14.

## Known limitations
- Follow-up questions are retrieved using the latest question only (no query rewriting).
- Citation validation checks that cited ids exist, not that each claim is semantically supported; that is measured in evals.
- Request deadline and injection guard: superseded by ADR 0005 (T09).
- The returned `quote` is the first 400 characters of the cited chunk, not the exact supporting span; the evidence panel opens the full chunk via `/api/documents/{id}/chunks/{chunk_id}`.
- `MAX_OUTPUT_TOKENS` (1000) includes reasoning tokens for reasoning models; truncated output returns 503 with a distinct message.
- Validation failures are logged by reason code only; inline citation markers from previous turns are stripped from history.
