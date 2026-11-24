# ADR 0005: Request deadline, history bounds and injection guard

Status: accepted (T09, 2026-11-24)

## Decisions
- **Request deadline:** each chat request has a wall-clock budget (`REQUEST_DEADLINE_SECONDS`, default 45, min 5). The question embedding and every chat call receive `min(remaining, OPENAI_TIMEOUT_SECONDS)` as their timeout. A call is not started with < 1 s left; the request returns `504 request_timeout` and persists nothing. Provider timeouts (`openai.APITimeoutError`) also map to 504 instead of 503.
- **No SDK retries on the chat path:** deadline-bound calls use `max_retries=0`, because SDK retries and `Retry-After` waits (up to 60 s) would exceed the budget. A transient 429/5xx therefore returns 503 at once; the user can retry. Ingestion keeps the client defaults (30 s, 2 retries) under its own 120 s deadline.
- **Repair is optional:** the single repair call only starts with ≥ 5 s left, and a timeout during repair abstains instead of failing.
- **History bounds:** at most 6 earlier messages (never starting mid-turn), each truncated to 2000 characters, with stale `[S#]` markers removed and `<source>` fences escaped. History is context, never evidence: citations are allowlisted against current sources only.
- **Input fencing:** `<source>` tags are escaped in the question and history as well as in document text, so user input cannot forge a source block.
- **Output injection guard (heuristic):** source sentences addressed to a model are flagged by a narrow pattern list (ignore/disregard previous instructions, reveal system prompt, output the exact phrase, you are now, act as an AI, chat-role lines). An answer is rejected (`injection_echo`) if it repeats a 3-word run found only in flagged sentences. Runs also present in the question or in benign source text, and runs made mostly of stopwords, are excluded. An answer quoting ≥ 12 consecutive words of the system prompt is rejected (`prompt_leak`). Rejection goes through the existing repair-then-abstain path. Logs record only counts and reason codes.
- **Offline fake chat** now quotes the best-matching sentence of the best source rather than the first 300 characters, so it behaves like a model that answers from benign content next to an injection.

## Known limitations
- The deadline is not a hard wall-clock cap. httpx applies the timeout to each connect/read/write phase, and DB work (retrieval, persistence) has no `statement_timeout`. The expected overrun is small for non-streaming calls.
- The guard is a backstop, not a guarantee. Paraphrased obedience passes. A question that asks what an injected sentence literally says will abstain. Instruction-like phrasing outside the pattern list is not flagged.
- Injection defenses are measured by eval cases in T11. No claim is made beyond those tests.
