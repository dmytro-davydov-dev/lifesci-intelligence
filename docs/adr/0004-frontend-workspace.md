# ADR 0004: Frontend workspace

Status: accepted (T07, 2026-11-24)

## Decisions
- **Three panels** (documents, assistant, evidence) in one client component; stacked on small screens, three columns from `lg`. State is local React state; no global store.
- **shadcn/ui on Radix** (`nova` preset). The CLI added itself as a runtime dependency only for `shadcn/tailwind.css` (~240 transitive packages); that MIT stylesheet is vendored as `src/app/shadcn-tailwind.css` instead. The Google `Geist` font the CLI adds was removed to keep builds offline; a system font stack is used.
- **Answers render as plain text**, never HTML or markdown. `[S1]` / `[S1, S2]` markers become buttons that open the evidence panel; unknown markers stay as text.
- **Evidence panel** fetches the full chunk (`/api/documents/{id}/chunks/{chunk_id}`) and links to the original file (`#page=N` for PDFs, opened in a new tab).
- **Scope:** checking documents restricts questions to them; none checked means all ready documents. Only ready documents are selectable.
- **Errors** show the API's message and request ID (`formatApiError`) for uploads, document list, chat and evidence; uploads report duplicates and failed ingestion inline. A failed question is removed from the transcript and restored to the input; a `conversation_not_found` response starts a new conversation.
- **Accessibility:** native buttons/inputs; one polite status line announces progress and results; selecting a citation moves focus to the evidence heading (important on stacked mobile layout); the hidden file input is removed from tab order.
- **Dependency hygiene:** exact pins; new packages limited to releases at least 14 days old (lucide-react 1.71.0, vitest 5.1.0, jsdom 31.0.0, jest-dom 7.0.1, user-event 14.6.9); installs run with `--ignore-scripts`. `cn@0.5.2` (shadcn-ui org, no dependencies, Node >= 22; Docker uses Node 24) is the CLI's replacement for clsx + tailwind-merge.

## Known limitations
- Conversation state is not restored after a page reload (the API persists it, but there is no list/load endpoint).
- No streaming; the UI waits for the full JSON answer.
