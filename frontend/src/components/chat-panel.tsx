"use client";

import { LoaderCircle, SendHorizontal } from "lucide-react";
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
    <section aria-labelledby="chat-heading" className="flex min-h-0 flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 id="chat-heading" className="text-sm font-semibold">
          Assistant
        </h2>
        <Button variant="ghost" size="sm" onClick={onNewConversation} disabled={pending || turns.length === 0}>
          New conversation
        </Button>
      </div>

      <p className="sr-only" role="status">
        {pending ? "Searching documents and drafting an answer." : announcement}
      </p>
      <div
        className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto rounded-lg border p-4"
        aria-label="Conversation"
        tabIndex={0}
      >
        {turns.length === 0 && (
          <div className="flex flex-col gap-2 text-sm text-muted-foreground">
            <p>Ask a question about your documents. Answers cite the exact passages they rely on.</p>
            <div className="flex flex-col items-start gap-2">
              {EXAMPLE_PROMPTS.map((prompt) => (
                <Button key={prompt} variant="outline" size="sm" disabled={!canAsk} onClick={() => submit(prompt)}>
                  {prompt}
                </Button>
              ))}
            </div>
            {!canAsk && <p>Upload a document to enable questions.</p>}
          </div>
        )}

        {turns.map((turn) =>
          turn.role === "user" ? (
            <div key={turn.id} className="self-end rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
              <span className="sr-only">You asked: </span>
              <p className="whitespace-pre-wrap">{turn.content}</p>
            </div>
          ) : (
            <article key={turn.id} className="flex flex-col gap-2 text-sm" aria-label="Assistant answer">
              {turn.status && turn.status !== "answered" && (
                <Badge variant="outline">{STATUS_LABEL[turn.status]}</Badge>
              )}
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
                <ul className="flex flex-wrap gap-1" aria-label="Sources">
                  {turn.citations.map((citation) => (
                    <li key={citation.chunk_id}>
                      <Button
                        variant="outline"
                        size="xs"
                        aria-pressed={citation.chunk_id === activeChunkId}
                        onClick={() => onSelectCitation(citation)}
                      >
                        {citation.label} · {citation.document_name}
                        {citation.page ? ` p. ${citation.page}` : ""}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ),
        )}

        {pending && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground" aria-hidden>
            <LoaderCircle className="size-4 animate-spin" aria-hidden /> Searching documents and drafting an answer…
          </p>
        )}
        <div ref={endRef} />
      </div>

      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <form onSubmit={handleSubmit} className="flex items-end gap-2">
        <label htmlFor="question" className="sr-only">
          Question
        </label>
        <Textarea
          id="question"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={canAsk ? "Ask about your documents… (Enter to send, Shift+Enter for a new line)" : "Upload a document first"}
          maxLength={MAX_QUESTION_CHARS}
          rows={2}
          disabled={!canAsk}
          className="min-h-0 resize-none"
        />
        <Button type="submit" size="icon-lg" disabled={pending || !canAsk || !draft.trim()} aria-label="Send question">
          {pending ? <LoaderCircle className="animate-spin" /> : <SendHorizontal />}
        </Button>
      </form>
      <p className="text-xs text-muted-foreground">
        Answers are generated from your documents for human review. Not medical advice or a compliance certification.
      </p>
    </section>
  );
}
