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

The sections below show how this worked in practice on this repository, drawn from the commit history, the review commits and the ADRs.

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
- Automated tests use deterministic fakes or scripted replies, so CI needs no API key and gives repeatable results.
- The comparison assessment labels (`evals/comparison-labels.json`) were derived from the corpus README's documented gaps. They are kept separate from the human-supplied golden dataset.
- The screenshots in `docs/screenshots/` are captured from the running app by Playwright (`E2E_SCREENSHOT_DIR`), not mocked.
- CI (`.github/workflows/ci.yml`) was run locally from a fresh clone, step by step, and passes on GitHub Actions.

