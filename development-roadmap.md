# Development roadmap — ASAP

All tasks start unchecked. Complete each exit gate before expanding scope. Estimates are not commitments; no deadline was supplied.

## Phase 0 — bootstrap (P0)
- [x] T01 Inspect repository; confirm runtime versions and model credentials availability without printing secrets.
- [x] T02 Scaffold frontend/backend, lock dependencies, .gitignore, .env.example and Compose (web/API/pgvector).
- [x] T03 Add migrations, health endpoints, fake provider and smoke test.
Exit: Compose starts and readiness succeeds. Commit only with human approval.

## Phase 1 — vertical slice (P0)
- [x] T04 Implement validated PDF/text upload, storage, status and duplicate handling.
- [ ] T05 Page-aware chunking, embeddings and atomic persistence; test failure paths.
- [ ] T06 Vector retrieval, scoped context, structured answer, citation validation and abstention.
- [ ] T07 Document library, chat, evidence panel and errors; connect real API.
- [ ] T08 Run upload-to-answer smoke test with synthetic fixture and opt-in live model.
Exit: working MVP vertical slice with citations and reproducible startup. Capture screenshot now.

## Phase 2 — reliability and evaluation (P0/P1)
- [ ] T09 Add conversation history bounds, input/output limits, timeout and injection defenses.
- [ ] T10 Add FTS/RRF hybrid retrieval and unit/integration tests.
- [ ] T11 Create 12-15 labeled eval cases (factual, comparison, unsupported, ambiguity, injection, extraction where implemented).
- [ ] T12 Run vector vs hybrid on same fixtures; record Recall@K, MRR, correctness/abstention and latency/cost when available.
- [ ] T13 Add optional LangSmith traces, redaction policy and trace failure isolation; structured logs.
Exit: deterministic tests pass; actual evaluation report exists (live runs marked unavailable if no key).

## Phase 3 — agentic differentiator (P1)
- [ ] T14 Implement LangGraph state, intent routing and model-selected read-only tools with bounded iterations.
- [ ] T15 Compare reference and SOP evidence; return structured findings with citations and uncertainty.
- [ ] T16 Test tool routing, budget exhaustion, invalid citations and missing evidence; add comparison evals.
Exit: live comparison demo or clearly documented fallback to Q&A; no fake tool execution.

## Phase 4 — submission (P0)
- [ ] T17 CI lint/typecheck/unit/integration/build; browser smoke where feasible.
- [ ] T18 Verify clean startup, reset procedure and demo fixture provenance; remove secrets and generated clutter.
- [ ] T19 Write architecture, ADRs, productionization, security and actual AI workflow notes; human revises README.
- [ ] T20 Capture screenshots and optionally record five-minute demo; final scope/limitations review.
Exit: repository is submission-ready; all claims backed by code or actual results.

## Phase 5 — only if time remains (P2)
- [ ] T21 FastMCP read-only tools with scope checks.
- [ ] T22 Cloud deployment, authentication and production storage if feasible.
- [ ] T23 Expand evals toward 40 cases; dashboard, exports, version comparison, SSE.

## Cut policy
Cut Phase 5 first, then separate comparison UI and SSE. Preserve ingestion, citations, abstention, tests, evals and setup. If Phase 3 cannot finish, ship the reliable Q&A and disclose the limitation. Never trade correctness for feature count.
