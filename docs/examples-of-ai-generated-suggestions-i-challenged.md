## Examples of AI-generated suggestions I challenged

### Summary of decisions

| Initial consideration | My decision | Rationale |
|---|---|---|
| Asynchronous ingestion workers | Synchronous ingestion | Reduce infrastructure complexity |
| Dedicated vector database | PostgreSQL + pgvector | Consolidate persistence and retrieval |
| Multiple autonomous agents | Bounded LangGraph workflows | Improve predictability and control |
| Langfuse | LangSmith | Simplify tracing and evaluation integration |
| 40 evaluation cases | 16 focused cases | Prioritize quality and delivery speed |
| Custom evaluation dashboard | LangSmith and generated reports | Avoid duplicating existing capabilities |
| Immediate MCP integration | Optional enhancement | Prioritize core functionality |
| Kubernetes | Docker Compose | Simplify deployment and reproducibility |

During the planning and development process, I used AI to explore architectural alternatives, identify potential risks and accelerate technical decision-making. However, I did not want to accept AI-generated recommendations without evaluating their relevance to the actual project requirements.

AI assistants can suggest technically valid solutions that introduce unnecessary complexity, particularly when designing systems from scratch. I challenged these suggestions based on business value, implementation effort, operational overhead, maintainability and the time available to deliver the MVP.

Some examples of these decisions are:

### Asynchronous ingestion vs. synchronous processing

An asynchronous ingestion pipeline with background workers and a message broker was considered. While this would be appropriate for processing large document collections in production, I decided that synchronous ingestion was sufficient for the initial MVP.

This reduced infrastructure complexity and allowed me to focus on validating the core document processing and retrieval pipeline. Asynchronous processing can be introduced later without fundamentally changing the application architecture.

### Dedicated vector database vs. PostgreSQL with pgvector

A dedicated vector database was considered as an alternative for semantic retrieval. However, I questioned whether maintaining an additional database was justified for the expected document volume.

I chose PostgreSQL with pgvector because it supports relational data, vector similarity search and full-text search within a single system. This simplifies deployment, persistence management and local development while providing the capabilities required for the MVP.

### Multiple autonomous agents vs. bounded agentic workflows

Rather than introducing multiple specialized autonomous agents, I preferred a controlled orchestration approach using LangGraph.

I wanted the execution flow to remain predictable, observable and testable. Multiple agents communicating with each other could introduce additional latency, token consumption and debugging complexity without necessarily improving answer quality.

My approach is to introduce agentic behavior where it solves a concrete problem, such as cross-document comparison or iterative evidence retrieval, rather than making every interaction agentic.

### Langfuse vs. LangSmith

Langfuse was initially suggested as the AI observability platform. After considering the planned use of LangGraph and the importance of evaluation experiments, I decided to use LangSmith instead.

The decision was based on integration simplicity and the ability to inspect agent execution, manage evaluation datasets and compare experiments within the same ecosystem.

I also wanted to avoid unnecessary vendor dependency, so LangSmith remains an optional integration rather than a mandatory runtime component.

### Large evaluation dataset vs. focused initial coverage

The initial recommendation was to create approximately 40 evaluation cases. Given the time constraints, I reduced the initial dataset to 16 carefully selected cases covering the most important failure scenarios.

I preferred a smaller, well-defined dataset with verifiable expected answers and source references over a larger dataset with questionable evaluation quality.

The dataset can be expanded incrementally as new failure patterns and edge cases are identified.

### Custom evaluation dashboard vs. existing tooling

A dedicated evaluation dashboard was considered as part of the application. However, I questioned the value of implementing functionality already provided by LangSmith.

I prioritized the evaluation harness itself, reproducible experiments and generated reports. Building a custom dashboard would have consumed development time without significantly improving the core product.

### MCP integration vs. core functionality

MCP integration is relevant to the intended architecture and provides an interesting opportunity to expose document intelligence capabilities to external AI clients.

However, I decided that it should not be a prerequisite for delivering the MVP. My priority was to establish a reliable document ingestion, retrieval and answer generation workflow before introducing additional integration interfaces.

### Kubernetes vs. Docker Compose

Although Kubernetes could be appropriate for a larger production deployment, I chose Docker Compose for the initial application.

My objective was to provide a reproducible environment that could be started and evaluated with minimal configuration. Kubernetes would have introduced additional infrastructure and operational complexity without addressing an immediate requirement.

### My approach to AI-generated recommendations

I use AI to expand the solution space, explore alternatives and challenge my own assumptions. However, I remain responsible for selecting the appropriate solution and validating the implementation.

I do not measure the effectiveness of AI-assisted development by the amount of generated code or the number of technologies introduced. I measure it by how quickly I can deliver reliable, maintainable software that addresses the actual problem.

For me, effective AI-assisted engineering means combining the speed and breadth of AI with human judgment, domain understanding, technical ownership and objective verification.
