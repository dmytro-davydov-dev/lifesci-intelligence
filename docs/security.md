# Security notes

This app is a single-user local demo. It makes no claim of production security or regulatory compliance. This document records the controls that are implemented and the gaps that are known.

## Implemented controls

| Area | Control | Where |
|---|---|---|
| Network | Every Compose port binds to 127.0.0.1. CORS is limited to the local web origin, and to the GET and POST methods. | `compose.yaml`, `app/main.py` |
| Containers | Non-root API user, `no-new-privileges`, all capabilities dropped. | `compose.yaml`, `backend/Dockerfile` |
| Uploads | Extension and magic-byte check, 10 MB and 100-page limits, request-size cap. Encrypted, scanned and empty PDFs are rejected. Names are sanitised; storage uses random keys, so a user-supplied path can never be followed. | ADR 0001 |
| Serving files | `X-Content-Type-Options: nosniff`, inline disposition, CSP `sandbox` for text files. | `app/api/documents.py` |
| Grounding | The model may cite only allowlisted labels (S1…). Quotes, pages and document IDs come from the database. Invalid citations get one repair attempt, then the request abstains. | ADR 0003, 0008 |
| Prompt injection | Retrieved text is fenced and escaped as untrusted data. An output guard rejects answers, finding topics and explanations that echo instructions found in sources or the system prompt. | ADR 0005 |
| Agent tools | Read-only tools only. There are no shell, web, write or generated-SQL tools. Document labels and source labels are checked against allowlists. Queries are truncated, and full-text search strips query operators. Step, search, context and time budgets apply. | ADR 0008 |
| Document scope | Requested document IDs are checked server-side (they must exist and be ready). Retrieval and every agent search are filtered to that scope. | `app/application/chat.py` |
| Availability | 45 s request deadline; provider timeouts are capped at the remaining budget; SDK retries are disabled inside the deadline; history and question length are bounded. | ADR 0005 |
| Secrets | No secrets are committed (checked in T18). `.env` is gitignored, and the API key is a `SecretStr`. Logs and traces never contain secrets, provider messages or document text by default. | ADR 0007 |
| Telemetry | LangSmith is off by default and uses app-specific environment variable names. LangChain and LangGraph auto-tracing are forced off even if `LANGSMITH_*` is set. Traces carry metadata only unless `TRACE_INCLUDE_CONTENT=true`, which is meant for approved synthetic data only. | ADR 0007, 0008 |
| Supply chain | Dependencies are pinned with committed lockfiles, and the packages added during T07 (frontend), T13 (langsmith) and T14 (langgraph) were chosen from releases at least two weeks old. CI actions are pinned to commit SHAs, and the CI token is read-only. | `uv.lock`, `package-lock.json`, `ci.yml` |

## Known gaps
- No authentication, authorization or tenant isolation: anyone who can reach the loopback ports can read every document.
- No encryption at rest beyond what the host provides. There is no retention or deletion policy, and no deletion endpoint.
- The injection guard is heuristic: an answer that obeys an injected instruction in paraphrase can pass. Retrieval itself can still be biased by adversarial text.
- Uploaded PDFs are parsed in the API process with PyMuPDF, without a sandbox or separate worker.
- The default database credentials (`lifesci/lifesci`) are only acceptable on loopback.
- There is no rate limiting. Synchronous ingestion holds a worker for up to 120 s.
- A live-model run has never been executed, so model-specific behaviours (refusals, injection susceptibility) are untested.

`docs/productionization.md` describes how these gaps would be closed.
