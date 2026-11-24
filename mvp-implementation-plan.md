# MVP implementation plan

Status: proposed, not implemented. Deadline unspecified; optimize for earliest runnable slice. Use the assignment and product design as scope; roadmap is the execution checklist.

## Scope and acceptance
- P0: PDF/text upload, document list/status, persistent chunks, vector retrieval, grounded conversational answers, clickable evidence, abstention, Compose, tests and reproducible evals.
- P1: hybrid retrieval, bounded model-driven comparison, LangSmith tracing, retrieval experiment and CI. Implement after P0 works; prioritize comparison and evals over polish.
- P2: FastMCP, cloud deployment, exports, dashboard, version comparison. No Kafka, Redis, Kubernetes, OCR or real patient data.
- Single-user local demo only; bind local ports to loopback. No claim of production security or compliance.

## Stack and boundaries
Next.js TypeScript + shadcn/ui; FastAPI Python + Pydantic; SQLAlchemy/Alembic; PostgreSQL + pgvector; PyMuPDF; OpenAI embeddings (text-embedding-3-small, 1536 dimensions) and configurable chat model; LangGraph; optional LangSmith; pytest, Playwright, Docker Compose, GitHub Actions. Pin compatible dependencies and commit lockfiles. Use uv for Python and npm for frontend. Verify installed versions before coding. No provider abstraction beyond small interfaces for embedding and generation.

Backend modules: api (routes/contracts), application (ingest/chat/compare use cases), domain (entities and policies), infrastructure (database, storage, model adapters), workflows (LangGraph). Keep framework and provider calls out of domain logic. Use dependency injection for fake providers in tests.

## Data and ingestion
- documents: UUID, name, sha256, media_type, version, storage_key, status, error, created_at; unique hash for duplicate uploads in demo.
- chunks: UUID, document_id FK, ordinal, page (1-based, null for text), section optional, text, embedding vector(1536), search tsvector; unique document_id/ordinal. Index FTS; exact vector search initially, HNSW only when measured need.
- conversations/messages: UUID, conversation_id, role, content, citations JSON, created_at. Bound history; never use previous assistant claims as evidence.
- Validate extension, signature, size (proposed 10 MB) and page limit (100); random storage keys, no user path traversal. Reject encrypted/scanned PDFs with actionable errors. Parse page-aware chunks (~500 tokens, 80 overlap initially); batch embeddings; transactionally publish chunks and ready status; failed documents excluded from retrieval. Synchronous bounded ingestion initially; move to durable jobs in production.

## API contract (proposed)
- GET /health/live; GET /health/ready (DB check).
- POST /api/documents multipart -> document metadata/status; GET /api/documents; GET /api/documents/{id}; GET /api/documents/{id}/chunks/{chunk_id} -> source passage; GET /api/documents/{id}/file -> original PDF for local viewing.
- POST /api/chat {conversation_id?, question, document_ids?, mode: auto|qa|compare} -> {conversation_id, answer, status: answered|insufficient_evidence|clarification, citations:[{chunk_id,document_id,page,quote}], findings?:[], trace_id?}. Start JSON; SSE optional. Validate document scope server-side; invalid IDs rejected. Consistent error envelope and request ID.

## Retrieval and generation
Baseline cosine similarity top 8; hybrid candidate pools 20 each, RRF k=60, final top 8; tune using evals. Apply selected document filters to both branches. Context budget proposed 6000 tokens, output 1000, max 3 retrieval rounds and 45-second request deadline; enforce provider timeouts and bounded retries. Model selects read-only search/list/get tools in comparison workflow; no shell, web or writes. Use structured output and allowlisted citation IDs; derive quotes/page metadata from database rather than trusting generated values. Reject invalid citations; one repair attempt then abstain. Treat retrieved text as untrusted evidence, not instructions. Comparison findings distinguish supported, potential gap and insufficient evidence; never certify compliance.

## UI
Three panels: document upload/list, chat with example prompts, evidence inspector. Render plain/sanitized markdown, no raw HTML. Show loading/errors, empty state and source links. Comparison findings may be rendered in chat rather than separate page. Responsive layout; keyboard accessible controls.

## Verification and operations
Unit tests for chunking, RRF, citation checks, budgets, injection fixtures; integration tests against pgvector with fake model; one browser smoke test upload-to-answer; opt-in live model evals. Initial 12-15 cases with gold evidence, expected facts/status, adversarial examples. Compare vector vs hybrid; report actual metrics and failures. CI runs lint/typecheck/tests/build without secrets. LangSmith disabled by default; enable only for approved public/synthetic fixtures, avoid raw sensitive traces, keep tracing failures nonfatal. Log request IDs, duration, token counts and error classes, not document text. Document backup, auth/RBAC, tenant isolation, encryption, retention, queues, monitoring, incident response and AWS deployment as future work.

## Definition of done
Fresh clone can run documented commands; demo fixture upload and question succeed; citations open exact evidence; unsupported question abstains; failure states work; tests and eval report are reproducible; README distinguishes implemented vs planned; screenshots captured from actual app. No fabricated results. Human reviews README rationale before submission.
