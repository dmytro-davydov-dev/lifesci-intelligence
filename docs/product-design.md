# LifeSci Intelligence — product design

## 3. Proposed product: Life Sciences Intelligence Assistant

LifeSci Intelligence is an evidence-grounded conversational assistant for pharmaceutical quality and regulatory documentation. Quality assurance managers and regulatory affairs specialists are the primary MVP personas; clinical research coordinators, compliance officers and operations managers are secondary users.
The business problem is time spent navigating SOPs, regulatory guidance, clinical protocols, quality assurance, safety and operational documentation. The product should return traceable answers, compare procedures and identify potential gaps, not merely return documents. It is not a clinical decision system or compliance certification tool.

## 4. Application design

Use a professional three-panel workspace: document library and upload on the left; conversational assistant and structured findings in the center; source evidence with page/section references and execution details on the right. Provide loading, empty, failure and insufficient-evidence states. A document comparison view and evaluation dashboard are enhancements. Example: compare a synthetic deviation SOP with ICH Q10, display potential gaps and let users inspect the evidence. Export findings only after the core experience works.

## 5. Key capabilities

Document-grounded Q&A: answer questions about responsibilities, deviation reporting, CAPA and risk assessment, with document references and source passages.
Cross-document analysis: identify documents, retrieve reference requirements, search the internal procedure for corresponding evidence, compare and synthesize structured findings, and flag insufficient evidence. Absence from retrieved passages is not proof of noncompliance.
Structured extraction: extract actions, responsible parties and sources; CSV/JSON export is optional.
Guardrails: abstain on unsupported questions, clarify ambiguity, validate citations and schemas, treat documents as untrusted data, detect conflicting versions where feasible, bound tokens and execution, and require human review for findings.

## 6. Recommended architecture

Use a modular monolith backend with a separate frontend. Next.js/React/TypeScript and shadcn/ui/Tailwind provide the workspace; FastAPI/Pydantic provide API validation; LangGraph provides bounded orchestration. PostgreSQL with pgvector and full-text search supports vector and keyword retrieval combined by reciprocal rank fusion (RRF). PyMuPDF parses PDFs; local file storage is sufficient for the MVP. Start with OpenAI text-embedding-3-small and a configurable OpenAI chat model; Anthropic is an alternative. FastMCP is optional.
Use LangSmith for AI tracing and experiment analysis (replacing the original Langfuse suggestion), structured application logging, pytest and Playwright, Docker Compose and GitHub Actions. Keep telemetry optional and redact sensitive inputs/outputs. OpenTelemetry is a later enhancement. Production target: AWS ECS Fargate, RDS PostgreSQL, S3, managed secrets, authentication and access control. Avoid Kafka, Redis, Kubernetes and Elasticsearch until justified.
Flow: browser -> FastAPI -> LangGraph -> shared retrieval / citation / ingestion services -> PostgreSQL, file storage and model provider. LangSmith observes execution out of band.

## 7. Agentic workflow

Route question intent to Q&A, comparison or extraction. Select read-only tools, retrieve evidence, assess sufficiency and optionally refine the query within a bounded loop. Generate structured output, validate citations and schema, then return or abstain. Clarify ambiguous requests. Tools: search_documents, get_document_section, list_documents, compare_sections, extract_requirements and validate_citations. Expose read-only retrieval through FastMCP only after core completion. Demonstrate actual model-selected tool calls, not just a fixed chain described as an agent.

## 8. Evaluation harness

Build version-controlled fixtures and deterministic checks independently of LangSmith. Original target: 40 cases (10 factual, 10 cross-document, 5 unanswerable, 5 ambiguous, 5 injection, 5 extraction). ASAP target: start with 12-15 cases and expand if time allows. Measure Recall@K, MRR, correctness, faithfulness, citation validity, abstention, injection resistance, schema validity, p95 latency and cost/query where measurable. Distinguish citation existence from claim support; manually review or use a calibrated judge for semantic support.
Compare vector-only, hybrid and hybrid with metadata filters using identical datasets and report actual results. Publish to LangSmith optionally. Never fabricate measurements; report sample size and limitations.

## 9. Document collection

Use public ICH Q9(R1), Q10 and optionally E6(R3) or relevant FDA CAPA guidance after verifying source/version and redistribution terms. Create clearly labeled synthetic SOPs for deviation management, corrective actions, risk assessment and document control. Start with 4-6 documents, including deliberately seeded gaps and conflicts with known expected answers. No real patient data. Record provenance and version; do not present synthetic procedures as regulatory guidance.

## 10. AI-assisted development approach

Keep frontend/, backend/, evals/datasets/, evals/evaluators/, evals/experiments/, evals/reports/, tests/, infrastructure/, sample-documents/, docs/adr/, .claude/agents/, .claude/skills/, .github/workflows/, CLAUDE.md, compose file and .env.example. Human defines acceptance criteria; AI proposes a plan; human reviews scope; AI implements and tests; independent review checks code/security; automated gates run; human approves commits. Record actual examples of rejected AI suggestions and corrected assumptions. Do not submit generated claims as personal experience.

## 11. Implementation roadmap

Original five-day concept: day 1 foundation/RAG; day 2 hybrid retrieval and frontend; day 3 agentic comparison and guardrails; day 4 evaluations and reliability; day 5 MCP, deployment and polish. For ASAP delivery, use exit-gated phases instead of fixed days: first vertical slice, then reliability, comparison/evals, submission. P0: ingestion, grounded answers, citations, UI, Compose, tests, evals and README. P1: hybrid retrieval, bounded agentic comparison, structured findings, guardrails, tracing, experiments and CI. P2: MCP, cloud deployment, evaluation dashboard, version comparison and exports. Cut P2 first.

