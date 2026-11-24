# LifeSci Intelligence

Evidence-grounded document intelligence for pharmaceutical quality and regulatory documentation. Newpage FDE take-home, Option 1.

**Status: Phases 0–3 complete and Phase 4 tasks T17, T18 and T20 done (offline-verified). Phase 4 is not complete: the author's README revision (part of T19) and an optional live-model run are pending.** Implemented: Compose stack, schema, health endpoints, fake model providers, validated PDF/text upload with duplicate detection and original-file viewing (`/api/documents`), page-aware chunking and embeddings (fake offline or OpenAI `text-embedding-3-small`) with atomic ready/failed status, grounded chat (`POST /api/chat`) with hybrid retrieval (vector + full-text, RRF; `RETRIEVAL_MODE=vector` for vector only), document scoping, validated citations derived from the database, one repair attempt and abstention; 45 s request deadline (504 on timeout), bounded history and a heuristic prompt-injection output guard (ADR 0005). Web workspace at http://127.0.0.1:3000: upload/list documents, scoped chat, clickable citations and evidence panel. Playwright browser smoke test (upload → answer → evidence → abstain). Evaluation runner comparing vector vs hybrid retrieval with an offline report (`evals/README.md`). Comparison agent (ADR 0008): LangGraph routes comparison questions (or `mode=compare`) to a bounded loop where the model picks read-only tools (list documents, search one document, read passage), then returns structured findings (supported / potential gap / insufficient evidence) with validated citations from at least two documents, rendered in chat (findings are not saved with the conversation). Not yet: live-model evaluation; the live-model smoke run has not been executed (no API key in this environment).

![Grounded Q&A with evidence](docs/screenshots/workspace-qa.png)

![Comparison with structured findings](docs/screenshots/workspace-comparison.png)

*Actual app, offline mode (`MODEL_PROVIDER=fake`), seeded synthetic corpus, captured by the Playwright smoke test (`E2E_SCREENSHOT_DIR`). Top: golden question E01 scoped to SOP-001-v2. Bottom: golden comparison E06 with two documents selected, showing the agent's findings and the cited evidence. The offline extractive stand-in is lexical, not a model: it quotes the documents' header lines rather than the 48-hour and 24-hour sentences, and it never judges alignment, so its only finding is "Insufficient evidence". Live-model output has not been captured (no API key).*

## Intended experience
Upload public or synthetic PDF/text documents, ask questions, inspect exact source passages and compare procedures against reference guidance. Findings are potential gaps for human review, not clinical advice or compliance certification.

## Documentation
| Topic | Document |
|---|---|
| Architecture, data model, request flows | [docs/architecture.md](docs/architecture.md) |
| Decisions and trade-offs | [docs/adr/](docs/adr/) (0001–0008) |
| Security controls and known gaps | [docs/security.md](docs/security.md) |
| Productionization plan (not implemented) | [docs/productionization.md](docs/productionization.md) |
| Evaluation method and results | [evals/README.md](evals/README.md) |
| AI-assisted workflow (factual notes) | [docs/ai-workflow.md](docs/ai-workflow.md) |

## Local setup
Prerequisites: Docker with Compose v2. For running checks outside containers: uv (Python 3.12) and Node 24 / npm.

```bash
cp .env.example .env          # optional; defaults work without it (MODEL_PROVIDER=fake, no key needed)
docker compose up --build --wait
curl http://127.0.0.1:8000/health/ready   # {"status":"ok","database":"ok"}
```

Web UI: http://127.0.0.1:3000 · API: http://127.0.0.1:8000 (docs at `/docs`) · Postgres: 127.0.0.1:5432. All ports bind to loopback only. The API applies Alembic migrations on startup.

**Reset:** `docker compose down -v && docker compose up --wait && docker compose exec api python -m app.seed`. The `-v` deletes the database and document-storage volumes, so all uploads and conversations are lost.

*Verified 2026-11-24 from a fresh clone at commit `0710cc0`:* a separate Compose project started healthy in about 20 s, the seed ingested 7 of 7 documents, the four Playwright smoke tests passed, and after `down -v` the library was empty and reseeding restored it.

### Test corpus
`lifesci-test-data/` is the version-controlled, fully synthetic corpus (fictional Northstar Biologics SOPs and a fictional reference; see its README). QMS-REF-001 is a controlled benchmark, not ICH or FDA guidance. A unit test checks that every seedable file is listed in `manifest.json` and marked `synthetic`. It is used for development, integration tests and evaluations:

| Path | Use |
|---|---|
| `sample-documents/` + `manifest.json` | Knowledge-base content; the only files the seed command ingests |
| `evals/golden-dataset.json` | Evaluation questions and expected answers; never ingested |
| `adversarial-documents/` | Prompt-injection fixtures; never seeded. Ingested only into throwaway `*_test` databases by `pytest -m security` and the evaluation harness, e.g. for golden case E15 |

```bash
docker compose exec api python -m app.seed      # seed the running stack
```
Compose mounts only `sample-documents/` and `manifest.json` (read-only) into the API container. Run the seed inside the container so files land in the shared storage volume and embeddings use the stack's configured provider. Seeding is idempotent: re-runs report `duplicate` and do not update stored metadata (reset with `docker compose down -v`, which deletes all local data). Paths are project-relative, so tests work unchanged in CI checkouts.

### Checks
```bash
cd backend && uv sync && uv run ruff check . && uv run ruff format --check . && uv run pytest
# integration tests need the Compose DB running; they create/migrate a separate *_test database:
TEST_DATABASE_URL=postgresql+psycopg://lifesci:lifesci@127.0.0.1:5432/lifesci_test REQUIRE_INTEGRATION=1 uv run pytest
TEST_DATABASE_URL=postgresql+psycopg://lifesci:lifesci@127.0.0.1:5432/lifesci_test REQUIRE_INTEGRATION=1 uv run pytest -m security   # adversarial fixtures only
cd frontend && npm ci && npm run lint && npm run typecheck && npm test && npm run build
# browser smoke against the running stack (docker compose up --build --wait):
cd frontend && npx playwright install chromium && npm run test:e2e
# optional: E2E_BASE_URL (default http://127.0.0.1:3000), E2E_SCREENSHOT_DIR=../docs/screenshots to save screenshots
```
Live-model smoke (opt-in, not run here): set `MODEL_PROVIDER=openai`, `OPENAI_API_KEY` and `OPENAI_CHAT_MODEL` in `.env`, reset and reseed (embeddings from different providers must not be mixed), then run `npm run test:e2e`.

LangSmith tracing is optional and off by default (`TRACE_LANGSMITH`, metadata only; ADR 0007).

## Architecture
Next.js + shadcn/ui -> FastAPI -> LangGraph chat graph (rule routing; grounded Q&A or a bounded read-only tool agent for comparisons) -> retrieval, ingestion and model adapters -> PostgreSQL + pgvector and local file storage. Hybrid full-text/vector retrieval fused with RRF. Optional metadata-only LangSmith tracing. Details: [docs/architecture.md](docs/architecture.md); also the [plan](mvp-implementation-plan.md), [roadmap](development-roadmap.md) and [product design](docs/product-design.md).

## Engineering and evaluation
Implemented: deterministic unit/integration tests, Playwright browser smoke, versioned evaluation fixtures with label checks, and an offline vector/hybrid comparison (`evals/reports/`, fake providers only; see `evals/README.md`). Structured JSON logs and optional, metadata-only LangSmith tracing (ADR 0007). CI runs lint, typecheck, unit/integration tests, builds and the browser smoke on pushes to `main` and on pull requests (`.github/workflows/ci.yml`; the same commands were verified locally from a fresh clone, but the workflow has not yet run on GitHub). Planned: live-model evaluation. See roadmap for status.

## Limitations (scope review, Phase 4)
- **No live-model run:** all answers, comparisons and evaluation numbers come from deterministic offline stand-ins or scripted test replies. Real answer quality, gap detection, latency and cost are unmeasured.
- **Comparison:** routing is a wording rule, so implicit comparisons need `mode=compare`. Findings are not saved with the conversation. Assessments are for human review, never a compliance determination.
- **Documents:** text-based PDF, TXT and MD only (no OCR or table extraction). Ingestion is synchronous, up to 10 MB and 100 pages.
- **Retrieval:** exact vector search (fine at demo scale). The section matching used in evaluations is heuristic.
- **Security:** single-user local demo with no authentication, encryption at rest or rate limiting. The injection guard is heuristic (see [docs/security.md](docs/security.md)).
- **Not built (Phase 5):** FastMCP tools, cloud deployment, exports, dashboard, SSE, version-aware comparison UI, a larger eval set.

## Productionization
Not production-ready: single-user local demo with no authentication. The proposed path is in [docs/productionization.md](docs/productionization.md): OIDC with RBAC and row-level tenant isolation, ECS Fargate, RDS pgvector, S3 with KMS, Secrets Manager, queued ingestion, eval-gated model changes, monitoring, backups and incident runbooks. Security controls and gaps: [docs/security.md](docs/security.md). No patient data or confidential documents.

## AI-assisted development and decisions
Factual workflow notes, including review findings and their outcomes: [docs/ai-workflow.md](docs/ai-workflow.md).

> **TODO (author, required to finish T19):** describe actual use, rejected suggestions, trade-offs and skipped standards in your own words. Also review the rest of this README; if a live-model run is done, record the model, configuration, failures and measured metrics.
