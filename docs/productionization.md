# Productionization plan (not implemented)

This plan is a proposal for taking the local demo to a regulated, multi-user deployment. None of it is built. The order follows risk: identity and data protection first, then reliability, then scale.

## 1. Identity, access and tenancy
- OIDC single sign-on through the customer's identity provider, using Amazon Cognito or a direct IdP integration. The API validates short-lived JWTs.
- RBAC roles: viewer, contributor (upload), QA reviewer, admin. Document-level access lists cover controlled documents.
- Tenant isolation in PostgreSQL through a `tenant_id` column on every table, with row-level security enforced from the request's identity. Each tenant gets its own S3 prefix and KMS key.
- An audit trail of who uploaded, asked, viewed evidence or exported what, kept in append-only storage. This is a prerequisite for GxP-style review; it would not certify the system.

## 2. AWS deployment
- **Compute:** ECS Fargate services for `web` and `api` in private subnets behind an ALB with AWS WAF.
- **Database:** RDS PostgreSQL with pgvector (Multi-AZ), automated backups, point-in-time recovery, and a tested restore runbook.
- **Files:** an S3 bucket replacing local storage, encrypted with KMS, versioned, public access blocked, with lifecycle rules for retention.
- **Secrets:** AWS Secrets Manager for provider and database credentials. Nothing secret goes in task definitions.
- **Delivery:** infrastructure as code with Terraform or CDK; separate dev, staging and prod accounts.

## 3. Reliable ingestion
- Uploads go to S3. An SQS queue feeds an ingestion worker service that parses in a resource-limited sandbox, embeds with retries and backoff, and publishes chunks atomically. Failed jobs go to a dead-letter queue.
- Document status is surfaced through polling or SSE.
- OCR (for example Amazon Textract) is an explicit opt-in for scanned documents. Table extraction would need an evaluation of its own.
- Document versioning with effective dates and supersession, so answers prefer current revisions and comparisons can target a specific revision.

## 4. Model operations
- An approved model list, with provider data-processing terms reviewed. Use regional endpoints or Amazon Bedrock where data residency requires it.
- Admission control at the API: per-user and per-tenant request rate limits and a cap on concurrent agent executions, returning HTTP 429 with a retry hint. Backed by a shared store once there is more than one API instance.
- Token and cost budgets enforced by the runtime, not only observed: estimate and reserve tokens and cost before each model call, reconcile with the provider's reported usage afterwards, and stop or degrade to a validated partial answer when the budget runs out. This extends the MVP's step, search, context, output-token and deadline limits (see [agent runtime and execution controls](agent-runtime-architecture-and-execution-controls.md)).
- Persistent usage accounting per request, user and tenant, built from the per-call `model_usage` token logs, feeding per-tenant quotas, cost dashboards and cost alerts.
- An eval gate in CI and before model or prompt changes: the golden set grown to 40 or more cases, live runs on synthetic data, and regression thresholds for recall, abstention, citation precision and comparison assessment accuracy.
- Human review loop: reviewers mark findings as confirmed or rejected, and that feedback feeds the evaluation data.

## 5. Observability and operations
- Ship the structured logs to CloudWatch or OpenTelemetry. Metrics: latency, error classes, abstention rate, agent stop reasons and token usage. Alarms are tied to SLOs.
- Tracing keeps the metadata-only default. Content tracing is enabled only in non-production with synthetic data.
- Incident response: an on-call runbook covering provider outage (degrade to retrieval-only evidence view), a suspected data leak, and a model misbehaviour report.
- Backups and disaster recovery: RDS snapshots plus S3 versioning, with a restore drill every quarter.

## 6. Security hardening
- Container image scanning and signing, plus dependency scanning (Dependabot or Renovate with review).
- Penetration test before handling real controlled documents, and threat-model review of the agent tools whenever a tool is added.
- Data retention and deletion workflows, including derived data: chunks, embeddings and traces.

## Explicitly out of scope
Real patient data, compliance certification, Kafka, Redis and Kubernetes. The current scale does not justify them.
