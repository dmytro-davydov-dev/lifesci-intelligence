# ADR 0006: Hybrid retrieval with reciprocal rank fusion

Status: accepted (T10, 2026-11-24). Default mode is to be confirmed by the T12 measurements.

## Decisions
- **Two branches, same filters:** exact cosine vector search and PostgreSQL full-text search (`to_tsvector('english', text)`, stored generated column with a GIN index from migration 0001). Both apply the ready-only filter and the server-validated `document_ids` scope.
- **Keyword query:** the question is reduced to unique alphanumeric terms (max 32), OR-joined and passed as a bound parameter to `to_tsquery('english', ...)`. OR semantics suit natural-language questions, where AND (`plainto_tsquery`/`websearch_to_tsquery`) rarely matches. Stripping everything but `[A-Za-z0-9]` means user text cannot inject tsquery operators. Ranking uses `ts_rank_cd`.
- **Fusion:** each branch returns 20 candidates. They are fused with RRF (`score = Σ 1/(60 + rank)`), and the final top 8 go to context selection. Ties break by best single rank, then chunk id, so results are deterministic. RRF needs no score normalisation between cosine and ts_rank.
- **Switchable:** `RETRIEVAL_MODE=vector|hybrid` (default `hybrid`), plus `RETRIEVAL_CANDIDATE_POOL` and `RRF_K`, so T12 can compare both modes on the same fixtures without code changes.

## Known limitations
- The English stemming config does not suit non-English documents.
- Hyphenated codes are split into terms (`QA-12` → `qa | 12`), which can over-match on common numbers.
- No similarity or rank threshold: weak matches still reach the model, which must abstain.
- There are two queries per question. This is fine at demo scale with exact search; HNSW would be added only when measured need arises.
