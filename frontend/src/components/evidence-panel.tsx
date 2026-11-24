"use client";

import { ExternalLink } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { type ChunkPassage, type Citation, documentFileUrl, formatApiError, getChunk } from "@/lib/api";
import { describeLocation } from "@/lib/citations";

type PassageResult =
  | { chunkId: string; state: "loaded"; passage: ChunkPassage }
  | { chunkId: string; state: "error"; message: string };

type PassageState = { state: "loading" } | PassageResult;

interface EvidencePanelProps {
  /** The selected citation; its passage is shown. */
  citation: Citation | null;
  /** All sources of the answer being inspected; defaults to just the selected citation. */
  citations?: Citation[];
  onSelect?: (citation: Citation) => void;
  /** Incremented when the user explicitly picks a citation; moves focus here. */
  focusRequest?: number;
}

export function EvidencePanel({ citation, citations = [], onSelect, focusRequest = 0 }: EvidencePanelProps) {
  const [result, setResult] = useState<PassageResult | null>(null);
  const [attempt, setAttempt] = useState(0);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (focusRequest === 0) return;
    headingRef.current?.scrollIntoView?.({ block: "start", behavior: "smooth" });
    headingRef.current?.focus({ preventScroll: true });
  }, [focusRequest]);

  useEffect(() => {
    if (!citation) return;
    let cancelled = false;
    const chunkId = citation.chunk_id;
    getChunk(citation.document_id, chunkId)
      .then((loaded) => {
        if (!cancelled) setResult({ chunkId, state: "loaded", passage: loaded });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setResult({
          chunkId,
          state: "error",
          message: formatApiError(error, "Could not load the source passage."),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [citation, attempt]);

  // A result for a different chunk means the newly selected passage is still loading.
  const passage: PassageState =
    citation && result?.chunkId === citation.chunk_id ? result : { state: "loading" };

  const sources = citation && !citations.some((c) => c.chunk_id === citation.chunk_id) ? [citation] : citations;

  return (
    <section
      aria-labelledby="evidence-heading"
      className="flex min-h-0 flex-col gap-4 rounded-xl border bg-card p-5 shadow-sm"
    >
      <h2 id="evidence-heading" ref={headingRef} tabIndex={-1} className="text-lg font-semibold outline-none">
        Source evidence
      </h2>
      {!citation ? (
        <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          Select a citation such as <span className="font-semibold">S1</span> to inspect the exact source passage.
        </div>
      ) : (
        <ul className="-mx-1 flex min-h-0 flex-col gap-3 overflow-y-auto px-1 pb-1" aria-label="Sources for this answer">
          {sources.map((source) => {
            const active = source.chunk_id === citation.chunk_id;
            return (
              <li
                key={source.chunk_id}
                className={`flex flex-col gap-2 rounded-lg border bg-muted px-4 py-3 text-sm ${
                  active ? "border-primary/50 ring-1 ring-primary/30" : ""
                }`}
              >
                <div className="min-w-0">
                  <p className="font-semibold">
                    [{source.label}] {source.document_name}
                  </p>
                  <p className="text-muted-foreground">{describeLocation({ ...source, document_name: "" }) || "Text document"}</p>
                </div>
                {active ? (
                  <>
                    {passage.state === "loading" && (
                      <div className="flex flex-col gap-2" role="status">
                        <span className="sr-only">Loading source passage</span>
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-4 w-11/12" />
                        <Skeleton className="h-4 w-4/5" />
                      </div>
                    )}
                    {passage.state === "error" && (
                      <Alert variant="destructive" role="alert">
                        <AlertDescription className="flex flex-col items-start gap-2">
                          {passage.message}
                          <Button variant="outline" size="xs" onClick={() => setAttempt((n) => n + 1)}>
                            Retry
                          </Button>
                        </AlertDescription>
                      </Alert>
                    )}
                    {passage.state === "loaded" && (
                      <blockquote
                        className="border-l-2 border-primary/60 pl-3 leading-relaxed whitespace-pre-wrap"
                        data-testid="evidence-passage"
                      >
                        {passage.passage.text}
                      </blockquote>
                    )}
                    <a
                      href={documentFileUrl(source.document_id, source.page)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
                    >
                      Open original{source.page ? ` at page ${source.page}` : ""}
                      <ExternalLink className="size-3.5" aria-hidden />
                    </a>
                  </>
                ) : (
                  onSelect && (
                    <button
                      type="button"
                      onClick={() => onSelect(source)}
                      className="self-start rounded-sm text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
                      aria-label={`View source passage ${source.label}: ${source.document_name}`}
                    >
                      View source passage
                    </button>
                  )
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
