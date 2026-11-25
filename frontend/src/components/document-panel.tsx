"use client";

import { FileStack, LoaderCircle, Plus, RefreshCw } from "lucide-react";
import { useRef, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { type DocumentSummary, formatApiError, uploadDocument } from "@/lib/api";
import { loadSampleDocuments } from "@/lib/samples";

const STATUS_VARIANT = {
  ready: "secondary",
  processing: "outline",
  failed: "destructive",
} as const;

interface DocumentPanelProps {
  documents: DocumentSummary[];
  loading: boolean;
  loadError: string | null;
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
  onUploaded: () => Promise<void> | void;
  onRefresh: () => void;
}

export function DocumentPanel({
  documents,
  loading,
  loadError,
  selectedIds,
  onToggle,
  onUploaded,
  onRefresh,
}: DocumentPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState<{ tone: "error" | "info"; text: string } | null>(null);

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    setNotice(null);
    try {
      const result = await uploadDocument(file);
      if (result.status === "failed") {
        setNotice({ tone: "error", text: `${result.name}: ${result.error ?? "ingestion failed"}` });
      } else if (result.duplicate) {
        setNotice({ tone: "info", text: `${result.name} was already uploaded.` });
      } else {
        setNotice({ tone: "info", text: `${result.name} is ready.` });
      }
      await onUploaded();
    } catch (error) {
      setNotice({ tone: "error", text: formatApiError(error, "Upload failed.") });
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleLoadSamples() {
    setUploading(true);
    setNotice(null);
    try {
      const { created, duplicate, failed } = await loadSampleDocuments();
      const parts = [`${created} added`, `${duplicate} already present`];
      if (failed.length > 0) parts.push(`failed: ${failed.join(", ")}`);
      setNotice({ tone: failed.length > 0 ? "error" : "info", text: `Sample documents: ${parts.join(", ")}.` });
      await onUploaded();
    } catch (error) {
      setNotice({ tone: "error", text: formatApiError(error, "Loading sample documents failed.") });
    } finally {
      setUploading(false);
    }
  }

  const readyCount = documents.filter((d) => d.status === "ready").length;

  return (
    <section aria-labelledby="documents-heading" className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 id="documents-heading" className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
          Document collection
        </h2>
        <Button variant="ghost" size="icon-sm" onClick={onRefresh} aria-label="Refresh documents">
          <RefreshCw />
        </Button>
      </div>

      <p className="text-xs text-muted-foreground">
        {selectedIds.size > 0
          ? `Asking ${selectedIds.size} selected document${selectedIds.size === 1 ? "" : "s"}`
          : `Asking all ${readyCount} ready document${readyCount === 1 ? "" : "s"}`}
      </p>

      {loadError && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      )}

      <ul className="-mx-2 flex min-h-0 flex-col gap-0.5 overflow-y-auto" aria-busy={loading}>
        {!loading && documents.length === 0 && (
          <li className="mx-2 rounded-lg border border-dashed border-sidebar-border bg-card/60 p-4 text-center text-sm text-muted-foreground">
            No documents yet. Upload one or load the synthetic samples to start asking questions.
          </li>
        )}
        {documents.map((document) => {
          const selectable = document.status === "ready";
          const selected = selectedIds.has(document.id);
          return (
            <li key={document.id}>
              <label
                className={`flex cursor-pointer items-start gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-sidebar-accent/60 has-disabled:cursor-default ${
                  selected ? "bg-sidebar-accent text-sidebar-accent-foreground" : ""
                }`}
              >
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 shrink-0 accent-primary"
                  checked={selected}
                  disabled={!selectable}
                  onChange={() => onToggle(document.id)}
                  aria-describedby={`doc-status-${document.id}`}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate" title={document.name}>
                    {document.name}
                  </span>
                  {selectable ? (
                    <span id={`doc-status-${document.id}`} className="sr-only">
                      {document.status}
                    </span>
                  ) : (
                    <Badge id={`doc-status-${document.id}`} variant={STATUS_VARIANT[document.status]} className="mt-1">
                      {document.status}
                    </Badge>
                  )}
                  {document.error && <span className="mt-1 block text-xs text-destructive">{document.error}</span>}
                </span>
              </label>
            </li>
          );
        })}
      </ul>

      <div className="mt-auto flex flex-col gap-2 pt-2">
        <input
          ref={inputRef}
          id="document-upload"
          type="file"
          accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          onChange={(event) => handleFile(event.target.files?.[0])}
          disabled={uploading}
        />
        <Button
          variant="outline"
          size="lg"
          className="w-full bg-card shadow-xs"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
        >
          {uploading ? <LoaderCircle className="animate-spin" /> : <Plus />}
          {uploading ? "Uploading and indexing…" : "Upload document"}
        </Button>
        <Button variant="ghost" size="sm" className="w-full" onClick={handleLoadSamples} disabled={uploading}>
          <FileStack />
          Load sample documents
        </Button>
        <p className="text-xs text-muted-foreground">PDF, TXT or MD · up to 10 MB · 100 pages. Public or synthetic documents only.</p>
        {notice && (
          <Alert variant={notice.tone === "error" ? "destructive" : "default"} role={notice.tone === "error" ? "alert" : "status"}>
            <AlertDescription>{notice.text}</AlertDescription>
          </Alert>
        )}
      </div>
    </section>
  );
}
