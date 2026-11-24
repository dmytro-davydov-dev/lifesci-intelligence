# Development roadmap — ASAP

All tasks start unchecked. Complete each exit gate before expanding scope. Estimates are not commitments; no deadline was supplied.

## Phase 0 — bootstrap (P0)
- [x] T01 Inspect repository; confirm runtime versions and model credentials availability without printing secrets.
- [x] T02 Scaffold frontend/backend, lock dependencies, .gitignore, .env.example and Compose (web/API/pgvector).
- [x] T03 Add migrations, health endpoints, fake provider and smoke test.
Exit: Compose starts and readiness succeeds. Commit only with human approval.

## Phase 1 — vertical slice (P0)
- [x] T04 Implement validated PDF/text upload, storage, status and duplicate handling.
- [x] T05 Page-aware chunking, embeddings and atomic persistence; test failure paths.
- [x] T06 Vector retrieval, scoped context, structured answer, citation validation and abstention.
- [x] T07 Document library, chat, evidence panel and errors; connect real API.
- [x] T08 Run upload-to-answer smoke test with synthetic fixture and opt-in live model. (Offline smoke automated with Playwright; live-model run not executed: no API key.)
Exit: working MVP vertical slice with citations and reproducible startup. Capture screenshot now.

## Phase 2 — reliability and evaluation (P0/P1)
- [x] T09 Add conversation history bounds, input/output limits, timeout and injection defenses.
- [x] T10 Add FTS/RRF hybrid retrieval and unit/integration tests.
- [x] T11 Create 12-15 labeled eval cases (factual, comparison, unsupported, ambiguity, injection, extraction where implemented). (16 user-supplied cases in lifesci-test-data/evals; labels verified against fixture text by tests.)
- [x] T12 Run vector vs hybrid on same fixtures; record Recall@K, MRR, correctness/abstention and latency/cost when available. (Offline fake-provider run in evals/reports; live run not executed: no API key; tokens/cost unavailable.)
- [x] T13 Add optional LangSmith traces, redaction policy and trace failure isolation; structured logs. (Live LangSmith run not executed: no key.)
Exit: deterministic tests pass; actual evaluation report exists (live runs marked unavailable if no key).

## Phase 3 — agentic differentiator (P1)
- [x] T14 Implement LangGraph state, intent routing and model-selected read-only tools with bounded iterations. (Offline/scripted providers only; live run not executed: no API key.)
- [x] T15 Compare reference and SOP evidence; return structured findings with citations and uncertainty. (Offline/scripted providers only; live run not executed: no API key.)
- [x] T16 Test tool routing, budget exhaustion, invalid citations and missing evidence; add comparison evals. (Assessment labels in evals/comparison-labels.json derived from the corpus README; offline run only, live run not executed: no API key.)
Exit: live comparison demo or clearly documented fallback to Q&A; no fake tool execution.

## Phase 4 — submission (P0)
- [x] T17 CI lint/typecheck/unit/integration/build; browser smoke where feasible. (.github/workflows/ci.yml; green on GitHub Actions at 7ccbb90.)
- [x] T18 Verify clean startup, reset procedure and demo fixture provenance; remove secrets and generated clutter. (Fresh-clone checks, Compose start, seed, smoke and reset verified; no secrets in tracked files; ignored local outputs left in place.)
- [x] T19 Write architecture, ADRs, productionization, security and actual AI workflow notes; human revises README. (docs/architecture.md, security.md, productionization.md, ai-workflow.md, engineering-standards.md, key-technical-and-product-decisions.md.)
- [x] T20 Capture screenshots and optionally record five-minute demo; final scope/limitations review. (Q&A and comparison screenshots captured by Playwright from the running app; demo video not recorded; limitations in README.)
Exit: repository is submission-ready; all claims backed by code or actual results.

## Phase 5 — only if time remains (P2)
- [ ] T21 FastMCP read-only tools with scope checks.
- [ ] T22 Cloud deployment, authentication and production storage if feasible.
- [ ] T23 Expand evals toward 40 cases; dashboard, exports, version comparison, SSE.

## Cut policy
Cut Phase 5 first, then separate comparison UI and SSE. Preserve ingestion, citations, abstention, tests, evals and setup. If Phase 3 cannot finish, ship the reliable Q&A and disclose the limitation. Never trade correctness for feature count.
