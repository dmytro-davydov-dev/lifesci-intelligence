# LifeSci Intelligence

Evidence-grounded document intelligence for pharmaceutical quality and regulatory documentation. Newpage FDE take-home, Option 1.

**Status: Phase 1 in progress.** Implemented: Compose stack, schema, health endpoints, fake model providers, validated PDF/text upload with duplicate detection and original-file viewing (`/api/documents`), page-aware chunking and embeddings (fake offline or OpenAI `text-embedding-3-small`) with atomic ready/failed status, grounded chat (`POST /api/chat`) with vector retrieval, document scoping, validated citations derived from the database, one repair attempt and abstention. Web workspace at http://127.0.0.1:3000: upload/list documents, scoped chat, clickable citations and evidence panel. Not yet: browser smoke test, hybrid retrieval, evals, comparison.

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

### Checks
```bash
cd backend && uv sync && uv run ruff check . && uv run ruff format --check . && uv run pytest
# integration tests need the Compose DB running; they create/migrate a separate *_test database:
TEST_DATABASE_URL=postgresql+psycopg://lifesci:lifesci@127.0.0.1:5432/lifesci_test REQUIRE_INTEGRATION=1 uv run pytest
cd frontend && npm ci && npm run lint && npm run typecheck && npm test && npm run build
```
LangSmith is optional and off by default (not yet wired).

## Architecture
Next.js + shadcn/ui -> FastAPI -> LangGraph -> retrieval/ingestion/model services -> PostgreSQL + pgvector and local file storage. Hybrid FTS/vector retrieval with RRF after baseline. Optional LangSmith tracing and experiment analysis. See [plan](mvp-implementation-plan.md), [roadmap](development-roadmap.md), [product design](docs/product-design.md).

## Engineering and evaluation
Planned: deterministic unit/integration tests, browser smoke, versioned evaluation fixtures, actual vector/hybrid comparison, structured logs and CI. No results yet. See roadmap for status. Record actual model/configuration, failures and measured metrics before submission.

## Productionization
Proposed AWS ECS Fargate, RDS, S3, managed secrets, auth/RBAC, tenant isolation, durable ingestion jobs, backups, monitoring and incident runbooks. Local demo is not production-ready. No patient data or confidential documents.

## AI-assisted development and decisions
Claude Code instructions, phase skill, eval skill and independent reviewer are provided. The author must document actual use, rejected suggestions, trade-offs and skipped standards in their own words. Before submission replace this planning README with verified setup, architecture, RAG decisions, evaluation results, screenshots, limitations and next steps. Do not claim planned features are implemented.
