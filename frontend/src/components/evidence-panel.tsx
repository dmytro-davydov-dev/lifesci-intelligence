"use client";

import { ExternalLink, Quote } from "lucide-react";
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
  citation: Citation | null;
  /** Incremented when the user explicitly picks a citation; moves focus here. */
  focusRequest?: number;
}

export function EvidencePanel({ citation, focusRequest = 0 }: EvidencePanelProps) {
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

  return (
    <section aria-labelledby="evidence-heading" className="flex min-h-0 flex-col gap-3">
      <h2 id="evidence-heading" ref={headingRef} tabIndex={-1} className="text-sm font-semibold outline-none">
        Evidence
      </h2>
      {!citation ? (
        <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          Select a citation such as <span className="font-semibold">S1</span> to inspect the exact source passage.
        </div>
      ) : (
        <div className="flex min-h-0 flex-col gap-3 overflow-y-auto rounded-lg border p-4">
          <div className="flex items-start gap-2 text-sm">
            <Quote className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
            <div className="min-w-0">
              <p className="font-semibold">{citation.label}</p>
              <p className="text-muted-foreground">{describeLocation(citation)}</p>
            </div>
          </div>
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
            <blockquote className="whitespace-pre-wrap border-l-2 pl-3 text-sm leading-relaxed" data-testid="evidence-passage">
              {passage.passage.text}
            </blockquote>
          )}
          <a
            href={documentFileUrl(citation.document_id, citation.page)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline"
          >
            Open original{citation.page ? ` at page ${citation.page}` : ""}
            <ExternalLink className="size-3.5" aria-hidden />
          </a>
        </div>
      )}
    </section>
  );
}
