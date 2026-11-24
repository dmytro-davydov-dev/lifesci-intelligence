# AI-Assisted Development

I used Claude Code as my primary AI coding assistant and ChatGPT during the initial product discovery, architectural discussions and implementation planning.

My approach was to treat AI as an active engineering collaborator rather than simply a code generation tool. I wanted to accelerate delivery while maintaining control over architecture, implementation quality, security and technical decisions.

## Development workflow

I structured the development process around small, well-defined implementation phases with clear requirements, priorities and acceptance criteria.

The repository contains several files that provide persistent context and make the development process repeatable:

- `CLAUDE.md` — project context, architectural principles, coding standards and development constraints.
- `mvp-implementation-plan.md` — functional and technical requirements.
- `development-roadmap.md` — implementation phases, tasks, priorities and progress tracking.
- `.claude/settings.json` — permissions and execution boundaries.
- `.claude/skills/` — reusable workflows for implementation and evaluation.
- `.claude/agents/` — dedicated subagents for independent code review.

The purpose of this structure is to reduce context loss between development sessions, minimize inconsistent implementation decisions and avoid repeatedly providing the same instructions.

My preferred development workflow is:

1. Define the problem, scope and acceptance criteria.
2. Ask the AI assistant to inspect the existing codebase and propose an implementation plan.
3. Review the plan and challenge unnecessary complexity or questionable assumptions.
4. Implement the functionality in small, manageable increments.
5. Verify the implementation through code review, automated tests and static analysis.
6. Update the documentation and development roadmap.

I prefer to keep architectural decisions and acceptance criteria under human control while delegating repetitive implementation tasks, test scaffolding, refactoring and documentation assistance to AI.

## Quality control and guardrails

AI-generated code should meet the same engineering standards as manually written code. I do not consider a feature complete simply because the AI assistant reports that it has implemented it.

My main principles are:

- Keep the scope of each implementation task limited to reduce the blast radius of changes.
- Avoid unrelated refactoring and unnecessary dependencies.
- Require explicit approval for significant architectural changes.
- Verify generated code against functional requirements and acceptance criteria.
- Use automated tests, type checking and linting as objective verification mechanisms.
- Separate implementation and review responsibilities where practical.
- Never expose secrets or sensitive information to AI tools unnecessarily.
- Do not accept generated evaluation results, performance metrics or claims without verification.

I also distinguish between deterministic software testing and AI evaluation. Traditional tests verify application behavior, API contracts, validation and business logic. AI evaluations measure retrieval quality, answer correctness, grounding, citation accuracy and the ability to abstain when evidence is insufficient.

Both are necessary because a technically correct application can still produce unreliable AI-generated answers.

# Key Technical and Product Decisions

## 1. Domain-specific product instead of a generic RAG chatbot

Given Newpage's focus on healthcare and life sciences, I decided to build a document intelligence assistant focused on pharmaceutical quality management and regulatory documentation.

I wanted to demonstrate how a relatively broad technical assignment could be translated into a concrete business use case.

The application is intended to help quality assurance and regulatory affairs professionals retrieve information, compare internal procedures against reference requirements and identify potential discrepancies.

I deliberately positioned the application as a decision-support tool rather than an automated regulatory compliance or clinical decision-making system. Traceability and human review are particularly important in this domain.

## 2. MVP-first development

Given the time constraints, I prioritized delivering a complete end-to-end workflow before introducing advanced functionality.

The initial objective was to establish a working vertical slice covering document ingestion, embedding generation, retrieval, answer generation and source citations.

More advanced capabilities, such as agentic document comparison, hybrid retrieval and evaluation experiments, were prioritized after the core workflow.

I deliberately avoided introducing infrastructure or abstractions that were not justified by the immediate requirements. A working, maintainable solution provides more value than a sophisticated architecture that cannot be reliably demonstrated.

## 3. Modular monolith instead of microservices

I chose a modular backend architecture with clearly separated responsibilities for document ingestion, retrieval, AI integration, orchestration and persistence.

This provides separation of concerns and testability without introducing the operational overhead of distributed services.

At the current scale, separate microservices, message brokers and Kubernetes would add complexity without providing a meaningful benefit. The architecture should nevertheless allow individual components to evolve independently if future requirements justify it.

## 4. Python and FastAPI for the backend

I selected Python because of its mature AI engineering ecosystem and integration with LLM providers, document processing libraries, orchestration frameworks and evaluation tools.

FastAPI provides asynchronous request handling, type validation, dependency injection and automatically generated API documentation.

I wanted to maintain a clear separation between application logic and infrastructure integrations, making components easier to test and replace.

## 5. Next.js, TypeScript and shadcn/ui for the frontend

I chose Next.js and TypeScript to build a maintainable, responsive frontend with strong typing and a modern React ecosystem.

I selected shadcn/ui because it provides customizable UI components without imposing a rigid visual design system. Having component source code directly in the repository also makes customization and AI-assisted development more straightforward.

The UI is designed around document exploration, conversational interaction and source evidence rather than simply replicating a conventional chatbot interface.

## 6. PostgreSQL and pgvector instead of a dedicated vector database

I chose PostgreSQL with pgvector because the application requires both relational data management and vector similarity search.

This allows document metadata, chunks, embeddings and other application data to be managed within the same database.

PostgreSQL also provides full-text search capabilities, making it possible to implement hybrid retrieval without introducing a separate search engine.

A dedicated vector database or search engine could become justified at a significantly larger scale, but I did not see a strong reason to introduce one for the MVP.

## 7. OpenAI for embeddings and language model inference

I selected OpenAI as the initial model provider to minimize integration complexity and accelerate development.

For embeddings, `text-embedding-3-small` provides a reasonable starting point for balancing retrieval quality, cost and performance.

I prefer to keep provider-specific functionality behind application-level interfaces wherever practical. This makes it easier to test the system using mocked responses, compare different models and introduce alternative providers without rewriting the core application logic.

Model selection should ultimately be driven by evaluation results rather than personal preference or assumptions about model capabilities.

## 8. Hybrid retrieval

Semantic similarity search is useful when users express concepts differently from the source documents. However, pharmaceutical documentation frequently contains exact identifiers, technical terminology, numerical thresholds and abbreviations.

For this reason, I chose to combine semantic retrieval with keyword-based search.

My intention is to evaluate both approaches against the same dataset and determine whether the additional retrieval complexity produces a measurable improvement.

I do not assume that hybrid retrieval is automatically superior for every query or document collection.

## 9. LangGraph for controlled agentic workflows

I selected LangGraph to support stateful, multi-step workflows where a single retrieval and generation step may not be sufficient.

Cross-document comparison is a good example. The application may need to identify relevant documents, retrieve evidence from multiple sources, assess evidence sufficiency and perform additional retrieval before generating structured findings.

I prefer bounded, observable agentic workflows over unrestricted autonomous agents. Execution limits, tool permissions, structured outputs and deterministic validation are important for controlling reliability, latency and cost.

For straightforward questions, a simpler RAG pipeline may be sufficient. Agentic orchestration should be used where it provides additional value rather than applied to every interaction by default.

## 10. LangSmith and a custom evaluation harness

I selected LangSmith because of its integration with LangGraph and its support for tracing, evaluation datasets, experiment comparison and AI observability.

However, I do not want application quality verification to depend entirely on an external platform.

The evaluation approach therefore combines LangSmith with a version-controlled evaluation dataset and a custom evaluation harness.

The custom harness is intended to support reproducible local execution, deterministic checks and automated regression testing. LangSmith complements this by providing detailed execution traces, experiment analysis and visibility into model behavior, token consumption and latency.

LangSmith should remain optional so that the core application can operate independently of the observability platform.

## 11. Evidence grounding and deterministic validation

One of the most important requirements for this application is that generated answers should be traceable to source documents.

I do not consider an LLM-generated citation sufficient evidence on its own. Citation identifiers should be validated against the retrieved source material, and the application should distinguish between supported findings and insufficient evidence.

Where possible, I prefer deterministic validation over asking another LLM to verify conditions that can be checked programmatically.

The application should also treat uploaded documents as untrusted data rather than executable instructions. This is particularly important for mitigating indirect prompt injection attacks.

## 12. Synthetic documents and reproducible evaluations

I chose to use a synthetic pharmaceutical document collection for the initial development and evaluation process.

The collection includes internal procedures, reference requirements, superseded document versions, intentionally introduced discrepancies and adversarial content.

This provides a controlled environment with known expected answers and source references, allowing retrieval and generation quality to be evaluated without using confidential pharmaceutical or patient information.

The evaluation dataset is kept separate from the knowledge base to prevent contamination of evaluation results.

## 13. Production readiness without premature infrastructure

For the MVP, I prioritized containerization, reproducible setup, automated testing, configuration management and observability over deploying a complex cloud infrastructure.

For a production deployment, I would additionally consider authentication, tenant isolation, document-level authorization, asynchronous ingestion, object storage, managed databases, secrets management, audit logging, rate limiting, backup and recovery, and infrastructure as code.

These decisions would depend on actual customer requirements, expected workloads, security constraints and data governance policies.

My general engineering philosophy is to introduce complexity when there is a demonstrated need for it, while keeping the architecture sufficiently modular to accommodate future requirements.

# Before submitting

Consider adding a section titled **Examples of AI-generated suggestions I challenged**. This could be one of the most valuable parts of the README because it demonstrates independent engineering judgment.

Potential examples from our planning discussions include:

| Initial consideration | Decision | Reason |
|---|---|---|
| Kafka or asynchronous ingestion workers | Synchronous ingestion initially | Faster MVP delivery |
| Dedicated vector database | PostgreSQL + pgvector | Reduced infrastructure complexity |
| Langfuse | LangSmith | LangGraph integration and evaluation workflows |
| Multiple autonomous agents | Bounded LangGraph workflows | Predictability and execution control |
| 40 initial evaluation cases | 16 controlled cases | Faster development with meaningful coverage |
| Custom evaluation dashboard | LangSmith and generated reports | Avoid duplicating existing capabilities |
| MCP integration in the initial release | Stretch goal | Prioritize the core product |
| Kubernetes | Docker Compose | Simpler setup and reviewer experience |

**Review note:** This draft is written in the first person based on our planning discussions and agreed architecture. The current implementation has not been inspected. Before submission, adjust it to reflect what you actually implemented and include two or three concrete examples from your Claude Code development sessions. Verify claims about completed features, tests, review workflows and evaluations. Remove this editorial note before submitting.
