---
name: run-evals
description: Run reproducible retrieval and answer quality evaluations and report measured results.
disable-model-invocation: true
---
Inspect eval dataset and runner. Validate fixture provenance, gold chunk IDs and expected statuses. Run deterministic tests first. Run live provider experiments only with explicit approval and configured credentials; do not read or print keys. Compare identical cases and settings except retrieval strategy. Record model, dataset version, configuration, sample size, failures, Recall@K, MRR and other available metrics. Separate citation existence from semantic support. Publish sanitized LangSmith results only if enabled and approved. Save actual results under evals/reports; mark unavailable metrics, never invent values.
