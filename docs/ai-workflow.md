# AI-assisted development: actual workflow notes

These are factual notes on how Claude Code was used to build this repository, drawn from the commit history and the review outcomes recorded there and in the ADRs. The author's own account, with opinions and the final rationale, belongs in the README and is written by the human.

## Setup
- `CLAUDE.md` sets the working agreement: exit-gated phases, typed boundaries, behavioural tests, no fabricated results, no secrets, and approval required for dependencies, pushes and deployments.
- Planning documents: `mvp-implementation-plan.md` (scope) and `development-roadmap.md` (task status; boxes are ticked only for verified work).
- Skills: `.claude/skills/implement-phase` (the phase workflow) and `.claude/skills/run-evals` (evaluation rules: no invented metrics, unavailable values marked).
- A read-only `reviewer` subagent (`.claude/agents/reviewer.md`) independently reviews grounding, scope, injection, secrets, timeouts and test gaps.

## How work proceeded
- Work moved one roadmap task at a time, each committed once its checks passed (ruff, pytest with integration tests on pgvector, frontend lint, typecheck, tests and build, and Playwright where the UI changed).
- The human set two standing rules during development: commit after each verified task, and implement the recommended option without asking. Both are recorded in Claude Code's project memory.
- Dependencies were proposed before installation, with exact pins and lockfile and transitive review:
  - `langsmith==0.14.17` (T13) and `langgraph==1.2.20` (T14) were explicitly approved by the human.
  - Packages added in T07 (frontend), T13 and T14 were chosen from releases at least two weeks old (recorded in those commits and in ADRs 0007 and 0008).
- The human supplied the synthetic corpus and the golden dataset. Tests verify the dataset's labels against the fixture text (T11) instead of trusting them.

## What reviews and tests caught
Taken from the review commits (the `T10 review`, `T12 review`, `T13 review` and `Phase 3 review` subjects) and the test history:

| Phase | Finding | Outcome |
|---|---|---|
| T08 | The browser smoke test found horizontal overflow on mobile and stale section labels from page headers. | Fixed |
| T10 review | Full-text terms were not Unicode-aware; the term cap counted stopwords; the candidate pool could be smaller than top-k. | Fixed |
| T12 | Random chunk UUIDs made tied rankings, and so the eval metrics, vary between ingestions. | Stable tie-breaks added |
| T12 review | The eval scored a separate retrieval rather than the answer's own; the runner could target a non-eval database. | Fixed; runner restricted to local `*_eval`/`*_test` databases |
| T13 review | The standard `LANGSMITH_*` variables would also switch on LangChain auto-tracing of full prompts. | App-specific variable names |
| T14 | Verified that an unguarded LangGraph run builds LangChain's tracer and posts full runs. | Graph runs inside `tracing_context(enabled=False)`; regression test |
| Phase 3 review | Comparison routing caught ordinary "difference" questions; a provider error mid-loop failed the whole request; finding topics escaped the injection check. | Partly adopted: "difference" removed from the routing rule (the reviewer's "explicit selection only" fix would have broken unselected comparisons); errors now degrade to the evidence already gathered; topics are checked |
| Phase 3 tests | A failed search set a stop reason, but the graph planned again. | Fixed (`plan` honours an existing stop) |
| Phase 3 review | No time limit on database search inside the agent; history resent on every planning call. | Deferred; documented in ADR 0008 |

## Verification discipline and limits
- No live-model run has been executed, because no API key was available. Every model behaviour in tests and reports comes from deterministic fakes or scripted replies, and the eval reports and README say so.
- The comparison assessment labels (`evals/comparison-labels.json`) were derived from the corpus README's documented gaps. They are kept separate from the human-supplied golden dataset.
- The screenshots in `docs/screenshots/` are captured from the running app by Playwright (`E2E_SCREENSHOT_DIR`), not mocked.
- CI (`.github/workflows/ci.yml`) has been run locally from a fresh clone, step by step, but not yet on GitHub.

## Left to the human
- The README narrative: product rationale, which AI suggestions were rejected and why, skipped standards, and personal trade-offs.
- Deciding whether to run a live evaluation (it costs money and needs an API key) and whether to push and deploy.
