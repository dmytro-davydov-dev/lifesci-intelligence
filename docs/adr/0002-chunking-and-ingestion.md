# ADR 0002: Chunking and synchronous ingestion

Status: accepted (T05, 2026-11-24)

## Decisions
- **Chunks never span pages**, so every PDF citation maps to exactly one 1-based page. Text/markdown chunks have `page = null`.
- **Size:** ~500 tokens with ~80 overlap, approximated as 4 characters/token (no tokenizer dependency). Windows are built from whole words and end at a sentence boundary when one exists in the second half of the window. Whitespace is normalized to single spaces; citation quotes will come from this stored text.
- **Sections:** markdown headings (`# Title`) and numbered headings (`4. Title`, `4.2 Title`: 1-2 digit parts with a period, capitalized, no sentence punctuation) set the section for following chunks and carry across pages. Heuristic; unknown layouts get `null`.
- **Scanned PDFs** are rejected before storage (`422 no_extractable_text`) when extracted text averages < 10 non-whitespace characters per page. No OCR.
- **Atomic publish:** chunks are embedded first (batches of 64), then chunks and `status=ready` are written in one transaction. Any embedding or persistence error leaves zero chunks and sets `status=failed` with a user-safe message (error class only; provider/DB messages are not stored or logged because they may echo document text).
- **Retry:** re-uploading identical bytes of a `failed` document atomically claims it (`failed -> processing`) and re-ingests it; ready/processing duplicates are returned unchanged.
- **Providers:** `MODEL_PROVIDER=fake` (default) uses a deterministic hashed bag-of-words embedder so offline tests get term-overlap similarity; it is not semantic. `MODEL_PROVIDER=openai` requires `OPENAI_API_KEY` at startup and uses `text-embedding-3-small` (1536 dims) with a 30 s timeout and 2 SDK retries.

## Known limitations
- Ingestion runs synchronously in the request. A process crash mid-ingestion, or a DB outage that also prevents marking the document `failed`, leaves it in `processing`; re-uploads return the stuck row and the only recovery is `docker compose down -v`. Production would use durable jobs with leases.
- Worst case per upload: batches are checked against a 120 s deadline (`INGESTION_DEADLINE_SECONDS`), but one in-flight call can still take up to 3 attempts x 30 s per httpx phase.
- Words longer than a chunk (e.g. base64 runs) are split into chunk-sized pieces.
- Duplicates are detected by hash before parsing; only failed duplicates are re-parsed.
