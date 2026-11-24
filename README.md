# LifeSci Intelligence

Evidence-grounded document intelligence for pharmaceutical quality and regulatory documentation. Newpage FDE take-home, Option 1.

**Status: Phase 3 in progress.** Implemented: Compose stack, schema, health endpoints, fake model providers, validated PDF/text upload with duplicate detection and original-file viewing (`/api/documents`), page-aware chunking and embeddings (fake offline or OpenAI `text-embedding-3-small`) with atomic ready/failed status, grounded chat (`POST /api/chat`) with hybrid retrieval (vector + full-text, RRF; `RETRIEVAL_MODE=vector` for vector only), document scoping, validated citations derived from the database, one repair attempt and abstention; 45 s request deadline (504 on timeout), bounded history and a heuristic prompt-injection output guard (ADR 0005). Web workspace at http://127.0.0.1:3000: upload/list documents, scoped chat, clickable citations and evidence panel. Playwright browser smoke test (upload → answer → evidence → abstain). Evaluation runner comparing vector vs hybrid retrieval with an offline report (`evals/README.md`). Comparison agent (ADR 0008): LangGraph routes comparison questions (or `mode=compare`) to a bounded loop where the model picks read-only tools (list documents, search one document, read passage), then answers from the gathered evidence with the same citation validation. Not yet: structured comparison findings, live-model evaluation; the live-model smoke run has not been executed (no API key in this environment).

![Workspace](docs/screenshots/phase1-workspace.png)

*Actual app, offline mode (`MODEL_PROVIDER=fake`), seeded corpus, captured by the Playwright smoke test. The offline extractive stand-in is lexical: here it cites SOP-001-v2 page 2, while the gold evidence for this question ("48 hours") is on page 1. Retrieval and answer quality are measured by the evaluation harness (Phase 2).*

## Intended experience
Upload public or synthetic PDF/text documents, ask questions, inspect exact source passages and compare procedures against reference guidance. Findings are potential gaps for human review, not clinical advice or compliance certification.

## Start implementation
1. Place this starter in a new Git repository and inspect the files.
2. Open Claude Code at the repository root (`claude`).
3. Run `/implement-phase` or ask Claude to read CLAUDE.md and execute Phase 0 only, then proceed through verified exit gates.
4. Review proposed dependency installs and commands before approval.

## Local setup
Prerequisites: Docker with Compose v2. For running checks outside containers: uv (Python 3.12) and Node 24 / npm.

```bash
cp .env.example .env          # optional; defaults work without it (MODEL_PROVIDER=fake, no key needed)
docker compose up --build --wait
curl http://127.0.0.1:8000/health/ready   # {"status":"ok","database":"ok"}
```

Web UI: http://127.0.0.1:3000 · API: http://127.0.0.1:8000 (docs at `/docs`) · Postgres: 127.0.0.1:5432. All ports bind to loopback only. The API applies Alembic migrations on startup. Reset local data with `docker compose down -v` (deletes the database volume).

### Test corpus
`lifesci-test-data/` is the version-controlled, fully synthetic corpus (fictional Northstar Biologics SOPs and a fictional reference; see its README). It is used for development, integration tests and evaluations:

| Path | Use |
|---|---|
| `sample-documents/` + `manifest.json` | Knowledge-base content; the only files the seed command ingests |
| `evals/golden-dataset.json` | Evaluation questions and expected answers; never ingested |
| `adversarial-documents/` | Prompt-injection fixtures; never seeded. Ingested only into throwaway `*_test` databases by `pytest -m security` and (from T11) the evaluation harness, e.g. for golden case E15 |

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
# optional: E2E_BASE_URL (default http://127.0.0.1:3000), E2E_SCREENSHOT=path.png to save a screenshot
```
Live-model smoke (opt-in, not run here): set `MODEL_PROVIDER=openai`, `OPENAI_API_KEY` and `OPENAI_CHAT_MODEL` in `.env`, reset and reseed (embeddings from different providers must not be mixed), then run `npm run test:e2e`.

LangSmith is optional and off by default (not yet wired).

## Architecture
Next.js + shadcn/ui -> FastAPI -> LangGraph -> retrieval/ingestion/model services -> PostgreSQL + pgvector and local file storage. Hybrid FTS/vector retrieval with RRF after baseline. Optional LangSmith tracing and experiment analysis. See [plan](mvp-implementation-plan.md), [roadmap](development-roadmap.md), [product design](docs/product-design.md).

## Engineering and evaluation
Implemented: deterministic unit/integration tests, Playwright browser smoke, versioned evaluation fixtures with label checks, and an offline vector/hybrid comparison (`evals/reports/`, fake providers only; see `evals/README.md`). Structured JSON logs and optional, metadata-only LangSmith tracing (ADR 0007). Planned: live-model evaluation and CI. See roadmap for status. Record actual model/configuration, failures and measured metrics before submission.

## Productionization
Proposed AWS ECS Fargate, RDS, S3, managed secrets, auth/RBAC, tenant isolation, durable ingestion jobs, backups, monitoring and incident runbooks. Local demo is not production-ready. No patient data or confidential documents.

## AI-assisted development and decisions
Claude Code instructions, phase skill, eval skill and independent reviewer are provided. The author must document actual use, rejected suggestions, trade-offs and skipped standards in their own words. Before submission replace this planning README with verified setup, architecture, RAG decisions, evaluation results, screenshots, limitations and next steps. Do not claim planned features are implemented.
