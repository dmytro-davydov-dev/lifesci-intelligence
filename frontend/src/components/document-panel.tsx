"use client";

import { FileText, LoaderCircle, RefreshCw, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { type DocumentSummary, formatApiError, uploadDocument } from "@/lib/api";

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

  const readyCount = documents.filter((d) => d.status === "ready").length;

  return (
    <section aria-labelledby="documents-heading" className="flex min-h-0 flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 id="documents-heading" className="text-sm font-semibold">
          Documents
        </h2>
        <Button variant="ghost" size="icon-sm" onClick={onRefresh} aria-label="Refresh documents">
          <RefreshCw />
        </Button>
      </div>

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
      <Button onClick={() => inputRef.current?.click()} disabled={uploading}>
        {uploading ? <LoaderCircle className="animate-spin" /> : <Upload />}
        {uploading ? "Uploading and indexing…" : "Upload PDF or text"}
      </Button>
      <p className="text-xs text-muted-foreground">PDF, TXT or MD · up to 10 MB · 100 pages. Public or synthetic documents only.</p>

      {notice && (
        <Alert variant={notice.tone === "error" ? "destructive" : "default"} role={notice.tone === "error" ? "alert" : "status"}>
          <AlertDescription>{notice.text}</AlertDescription>
        </Alert>
      )}
      {loadError && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      )}

      <p className="text-xs text-muted-foreground">
        {selectedIds.size > 0
          ? `Asking ${selectedIds.size} selected document${selectedIds.size === 1 ? "" : "s"}`
          : `Asking all ${readyCount} ready document${readyCount === 1 ? "" : "s"}`}
      </p>

      <ul className="flex min-h-0 flex-col gap-1 overflow-y-auto" aria-busy={loading}>
        {!loading && documents.length === 0 && (
          <li className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
            No documents yet. Upload one to start asking questions.
          </li>
        )}
        {documents.map((document) => {
          const selectable = document.status === "ready";
          return (
            <li key={document.id} className="rounded-lg border p-2">
              <label className="flex cursor-pointer items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={selectedIds.has(document.id)}
                  disabled={!selectable}
                  onChange={() => onToggle(document.id)}
                  aria-describedby={`doc-status-${document.id}`}
                />
                <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium" title={document.name}>
                    {document.name}
                  </span>
                  <Badge id={`doc-status-${document.id}`} variant={STATUS_VARIANT[document.status]}>
                    {document.status}
                  </Badge>
                  {document.error && <span className="mt-1 block text-xs text-destructive">{document.error}</span>}
                </span>
              </label>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
