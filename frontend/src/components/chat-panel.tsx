"use client";

import { ArrowRight, LoaderCircle } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { AnswerText } from "@/components/answer-text";
import { FindingsList } from "@/components/findings-list";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { AnswerStatus, Citation, Finding } from "@/lib/api";

export interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: AnswerStatus;
  citations?: Citation[];
  findings?: Finding[];
}

const EXAMPLE_PROMPTS = [
  "Within how many hours must a deviation be reported?",
  "Who is responsible for approving CAPA actions?",
  "What does the procedure say about risk assessment?",
  "Compare deviation reporting deadlines in the SOP and the reference.",
];

const STATUS_LABEL: Record<Exclude<AnswerStatus, "answered">, string> = {
  insufficient_evidence: "Insufficient evidence",
  clarification: "Clarification needed",
};

const MAX_QUESTION_CHARS = 2000;

interface ChatPanelProps {
  turns: ChatTurn[];
  pending: boolean;
  error: string | null;
  canAsk: boolean;
  activeChunkId: string | null;
  /** Resolves true when answered; on false the draft is kept so the user can retry. */
  onAsk: (question: string) => Promise<boolean>;
  onSelectCitation: (citation: Citation) => void;
  onNewConversation: () => void;
}

export function ChatPanel({
  turns,
  pending,
  error,
  canAsk,
  activeChunkId,
  onAsk,
  onSelectCitation,
  onNewConversation,
}: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const lastTurn = turns.at(-1);
  const announcement =
    lastTurn?.role === "assistant"
      ? lastTurn.status === "answered"
        ? `Answer received with ${lastTurn.citations?.length ?? 0} source(s).`
        : `${STATUS_LABEL[lastTurn.status as Exclude<AnswerStatus, "answered">] ?? "Answer received"}.`
      : "";

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [turns.length, pending]);

  async function submit(question: string) {
    const trimmed = question.trim();
    if (!trimmed || pending || !canAsk) return;
    setDraft("");
    if (!(await onAsk(trimmed))) setDraft(trimmed);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submit(draft);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit(draft);
    }
  }

  return (
    <section
      aria-labelledby="chat-heading"
      className="flex min-h-[32rem] flex-col gap-4 rounded-xl border bg-card p-5 shadow-sm lg:min-h-0"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 id="chat-heading" className="text-xl font-semibold">
            Quality intelligence
          </h2>
          <p className="text-sm text-muted-foreground">Ask questions across your document collection</p>
        </div>
        <Button variant="ghost" size="sm" onClick={onNewConversation} disabled={pending || turns.length === 0}>
          New conversation
        </Button>
      </div>

      <p className="sr-only" role="status">
        {pending ? "Searching documents and drafting an answer." : announcement}
      </p>
      <div
        className="-mx-1 flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-1 py-1"
        aria-label="Conversation"
        tabIndex={0}
      >
        {turns.length === 0 && (
          <div className="flex flex-col gap-3 text-sm text-muted-foreground">
            <p>Ask a question about your documents. Answers cite the exact passages they rely on.</p>
            <div className="flex flex-col items-start gap-2">
              {EXAMPLE_PROMPTS.map((prompt) => (
                <Button
                  key={prompt}
                  variant="outline"
                  size="sm"
                  className="h-auto max-w-full justify-start py-1.5 text-left whitespace-normal"
                  disabled={!canAsk}
                  onClick={() => submit(prompt)}
                >
                  {prompt}
                </Button>
              ))}
            </div>
            {!canAsk && <p>Upload a document to enable questions.</p>}
          </div>
        )}

        {turns.map((turn) =>
          turn.role === "user" ? (
            <div
              key={turn.id}
              className="max-w-[90%] self-end rounded-lg bg-secondary px-4 py-3 text-sm text-secondary-foreground"
            >
              <span className="sr-only">You asked: </span>
              <p className="whitespace-pre-wrap">{turn.content}</p>
            </div>
          ) : (
            <article key={turn.id} className="flex flex-col gap-3 text-sm" aria-label="Assistant answer">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="size-6 shrink-0 rounded-full bg-primary" aria-hidden />
                <span className="font-semibold">Evidence-based analysis</span>
                {turn.status && turn.status !== "answered" && (
                  <Badge variant="outline">{STATUS_LABEL[turn.status]}</Badge>
                )}
              </div>
              <AnswerText
                answer={turn.content}
                citations={turn.citations ?? []}
                activeChunkId={activeChunkId}
                onSelect={onSelectCitation}
              />
              {turn.findings && turn.findings.length > 0 && (
                <FindingsList
                  findings={turn.findings}
                  citations={turn.citations ?? []}
                  activeChunkId={activeChunkId}
                  onSelect={onSelectCitation}
                />
              )}
              {turn.citations && turn.citations.length > 0 && (
                <ul className="flex flex-wrap gap-x-3 gap-y-1" aria-label="Sources">
                  {turn.citations.map((citation) => (
                    <li key={citation.chunk_id}>
                      <button
                        type="button"
                        aria-pressed={citation.chunk_id === activeChunkId}
                        onClick={() => onSelectCitation(citation)}
                        className="rounded-sm text-xs text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring aria-pressed:font-semibold aria-pressed:underline"
                      >
                        [{citation.label}] {citation.document_name}
                        {citation.page ? `, p. ${citation.page}` : ""}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ),
        )}

        {pending && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground" aria-hidden>
            <LoaderCircle className="size-4 animate-spin text-primary" aria-hidden /> Searching documents and drafting an
            answer…
          </p>
        )}
        <div ref={endRef} />
      </div>

      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col gap-2">
        <form
          onSubmit={handleSubmit}
          className="flex items-end gap-2 rounded-lg border border-input bg-card p-2 pl-3 transition-shadow focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30"
        >
          <label htmlFor="question" className="sr-only">
            Question
          </label>
          <Textarea
            id="question"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={canAsk ? "Ask a follow-up question… (Shift+Enter for a new line)" : "Upload a document first"}
            maxLength={MAX_QUESTION_CHARS}
            rows={1}
            disabled={!canAsk}
            className="max-h-40 min-h-9 resize-none border-0 bg-transparent px-0 py-1.5 shadow-none focus-visible:ring-0 dark:bg-transparent"
          />
          <Button type="submit" size="icon-lg" disabled={pending || !canAsk || !draft.trim()} aria-label="Send question">
            {pending ? <LoaderCircle className="animate-spin" /> : <ArrowRight />}
          </Button>
        </form>
        <p className="text-xs text-muted-foreground">
          Answers are generated from your documents for human review. Not medical advice or a compliance certification.
        </p>
      </div>
    </section>
  );
}
