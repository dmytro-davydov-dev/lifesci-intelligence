# Engineering Standards Followed and Skipped

The goal was a small, well-tested and reproducible solution rather than a feature-complete one. These are the standards I applied, and the ones I consciously skipped for an MVP-sized local demo.

## Followed

### Code structure
- **Layered modular monolith.** The backend is split into `api` (routes and contracts), `application` (ingest, chat and compare use cases), `domain` (entities and policies), `infrastructure` (database, storage, model adapters) and `workflows` (LangGraph). The domain layer imports no FastAPI, SQLAlchemy or provider SDKs.
- **Typed boundaries.** Pydantic models for the API contracts and settings. TypeScript in `strict` mode on the frontend.
- **Dependency injection.** Embedding and generation providers sit behind small interfaces, so tests use deterministic fakes and no test needs network access or an API key.
- **No speculative abstractions.** Only one provider abstraction (embedding and generation). There is no generic plugin system and no microservices.

### Quality gates
- **Linting and formatting.** Ruff (`E`, `F`, `I`, `B`, `UP`, `S` security rules, `SIM`) plus `ruff format --check` for the backend. ESLint and `tsc --noEmit` for the frontend.
- **Behavioural tests.** Unit tests for the pure domain logic (chunking, RRF fusion, citation validation, budgets, injection checks, intent routing). Integration tests run against real PostgreSQL with pgvector, not mocks. Security tests use adversarial documents. Frontend component tests use Vitest. A Playwright browser smoke test covers upload to cited answer.
- **CI.** `.github/workflows/ci.yml` runs lint, format, typecheck, unit and integration tests, builds, and the browser smoke against the Compose stack on every push to `main` and every pull request. It needs no secrets.
- **Reproducible evaluations.** A versioned golden dataset, label checks against the fixture text, and a vector-vs-hybrid report in `evals/reports/`. The report says plainly which values are unavailable instead of estimating them.

### Dependencies and environments
- **Pinned dependencies and lockfiles.** `uv.lock` and `package-lock.json` are committed. CI uses `uv sync --locked` and `npm ci`. New packages were reviewed (lockfile and transitive dependencies) before installation.
- **Containerised and reproducible.** One `docker compose up --build --wait` starts the web app, the API and pgvector, with health checks. Migrations run on startup, and the reset and seed procedure is documented and verified from a fresh clone.
- **Twelve-factor configuration.** Everything is configured through environment variables, with a committed `.env.example`. The defaults run offline (`MODEL_PROVIDER=fake`).

### Security, reliability and observability
- **Secure defaults for a local demo.** Ports bind to loopback only and containers run as non-root users. Uploads are validated by extension, file signature, size and page count. Storage keys are random, so user input never reaches file paths. No secrets live in the repository.
- **LLM-specific guardrails.** Retrieved text is treated as untrusted data. Citations are restricted to allowlisted chunk IDs, and their quotes and page numbers come from the database, not from the model. The assistant abstains when evidence is insufficient. Context, output, iteration and time budgets are bounded.
- **Observability.** Structured JSON logs carry request IDs, durations and error classes but never document text. Errors use one consistent envelope. Health endpoints cover liveness and readiness (database check). LangSmith tracing is optional, records metadata only, and a tracing failure never breaks a request.

### Process
- **Decision records.** ADRs 0001–0008 in `docs/adr/` record the trade-offs at the moment each decision was made.
- **Small, verified increments.** One roadmap task at a time, each committed only after its checks passed. The roadmap is ticked only for verified work.

## Skipped (and why)

| Standard | Why skipped | What production would need |
|---|---|---|
| Authentication, authorisation, multi-tenancy | Single-user local demo | OIDC, RBAC, row-level tenant isolation (see `productionization.md`) |
| Rate limiting and admission control | No shared deployment | Per-user and per-tenant limits, token and cost budgets |
| Static type checking for Python (mypy or pyright) | Pydantic and typed signatures covered the boundaries; the time went to behavioural tests | Add pyright in strict mode to CI |
| Coverage thresholds | Tests target behaviour, and a percentage gate encourages low-value tests | Track coverage as a signal, not a gate |
| Pre-commit hooks | CI and the documented check commands enforce the same gates | Add pre-commit for faster local feedback |
| Dependency and image scanning (Dependabot, SAST, container scanning) | Manual review of pins and lockfiles at this scale | Dependabot or Renovate, CodeQL, image scanning in CI |
| Pull-request workflow with branch protection | Solo project with linear commits on `main` | Protected `main`, required reviews and CI checks |
| Durable background jobs for ingestion | Synchronous bounded ingestion is simpler and enough for a demo | A queue with workers, retries and idempotency |
| Encryption at rest, backups, retention policies | Local Docker volumes with synthetic data only | KMS-encrypted storage, automated backups, retention rules |
| Load and performance testing | Demo-scale corpus; exact vector search is fast enough | Load tests and an HNSW index once measured need appears |
| Live-model evaluation in CI | Needs paid API keys and gives non-deterministic results | A scheduled, opt-in live eval gate before model or prompt changes |
| Formal accessibility audit | Keyboard-accessible controls and semantic markup only | Automated axe checks plus a manual WCAG review |
| Database migration rollback tests | Forward-only migrations on a fresh local database | Tested downgrade paths, or expand-and-contract migrations |
