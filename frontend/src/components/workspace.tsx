"use client";

import { Plus } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiStatus } from "@/components/api-status";
import { type ChatTurn, ChatPanel } from "@/components/chat-panel";
import { DocumentPanel } from "@/components/document-panel";
import { EvidencePanel } from "@/components/evidence-panel";
import { ApiError, type Citation, type DocumentSummary, formatApiError, listDocuments, sendChat } from "@/lib/api";

export function Workspace() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [pending, setPending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const [evidenceCitations, setEvidenceCitations] = useState<Citation[]>([]);
  const [focusRequest, setFocusRequest] = useState(0);
  const latestRefresh = useRef(0);

  const refreshDocuments = useCallback(async () => {
    const requestNumber = ++latestRefresh.current;
    setDocumentsLoading(true);
    try {
      const result = await listDocuments();
      if (requestNumber !== latestRefresh.current) return; // a newer refresh superseded this one
      setDocuments(result);
      setDocumentsError(null);
      const ready = new Set(result.filter((d) => d.status === "ready").map((d) => d.id));
      setSelectedIds((current) => new Set([...current].filter((id) => ready.has(id))));
    } catch (error) {
      if (requestNumber === latestRefresh.current) {
        setDocumentsError(formatApiError(error, "Could not load documents."));
      }
    } finally {
      if (requestNumber === latestRefresh.current) setDocumentsLoading(false);
    }
  }, []);

  useEffect(() => {
    // One-time initial load; refreshDocuments sets a loading flag before fetching.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshDocuments();
  }, [refreshDocuments]);

  function toggleDocument(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function ask(question: string): Promise<boolean> {
    setChatError(null);
    setPending(true);
    const turnId = crypto.randomUUID();
    setTurns((current) => [...current, { id: turnId, role: "user", content: question }]);
    try {
      const response = await sendChat({
        question,
        conversation_id: conversationId,
        document_ids: selectedIds.size > 0 ? [...selectedIds] : undefined,
      });
      setConversationId(response.conversation_id);
      setTurns((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: response.answer,
          status: response.status,
          citations: response.citations,
          findings: response.findings ?? [],
        },
      ]);
      if (response.citations[0]) {
        setActiveCitation(response.citations[0]);
        setEvidenceCitations(response.citations);
      }
      return true;
    } catch (error) {
      // Drop the unanswered turn; the question goes back into the input for retry.
      setTurns((current) => current.filter((turn) => turn.id !== turnId));
      if (error instanceof ApiError && error.code === "conversation_not_found") {
        setConversationId(undefined);
        setTurns([]);
        setChatError("The previous conversation is no longer available. Send again to start a new one.");
      } else {
        setChatError(formatApiError(error, "The question could not be answered."));
      }
      return false;
    } finally {
      setPending(false);
    }
  }

  function selectCitation(citation: Citation) {
    setActiveCitation(citation);
    // Show the sources of the answer the citation belongs to (latest match wins).
    const owner = turns.findLast((turn) => turn.citations?.some((c) => c.chunk_id === citation.chunk_id));
    if (owner?.citations) setEvidenceCitations(owner.citations);
    setFocusRequest((n) => n + 1);
  }

  function newConversation() {
    setTurns([]);
    setConversationId(undefined);
    setActiveCitation(null);
    setEvidenceCitations([]);
    setChatError(null);
  }

  const hasReadyDocuments = documents.some((d) => d.status === "ready");

  return (
    <div className="flex min-h-screen flex-col bg-background lg:h-screen">
      <header className="flex flex-wrap items-center justify-between gap-2 bg-header px-4 py-3 text-header-foreground sm:px-6">
        <div className="flex items-center gap-3">
          <span className="grid size-9 place-items-center rounded-lg bg-primary text-primary-foreground" aria-hidden>
            <Plus className="size-5" strokeWidth={3} />
          </span>
          <div>
            <h1 className="text-lg font-semibold leading-tight">LifeSci Intelligence</h1>
            <p className="hidden text-xs text-header-foreground/70 sm:block">
              Evidence-grounded Q&amp;A for pharmaceutical quality documentation
            </p>
          </div>
        </div>
        <ApiStatus />
      </header>
      <div className="grid flex-1 grid-cols-1 lg:min-h-0 lg:grid-cols-[minmax(240px,280px)_minmax(0,1fr)] lg:grid-rows-[minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col border-b border-sidebar-border bg-sidebar p-4 text-sidebar-foreground lg:border-r lg:border-b-0">
          <DocumentPanel
            documents={documents}
            loading={documentsLoading}
            loadError={documentsError}
            selectedIds={selectedIds}
            onToggle={toggleDocument}
            onUploaded={refreshDocuments}
            onRefresh={refreshDocuments}
          />
        </aside>
        <main className="grid grid-cols-1 gap-4 p-4 lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_minmax(280px,360px)] lg:grid-rows-[minmax(0,1fr)]">
          <ChatPanel
            turns={turns}
            pending={pending}
            error={chatError}
            canAsk={hasReadyDocuments}
            activeChunkId={activeCitation?.chunk_id ?? null}
            onAsk={ask}
            onSelectCitation={selectCitation}
            onNewConversation={newConversation}
          />
          <EvidencePanel
            citation={activeCitation}
            citations={evidenceCitations}
            focusRequest={focusRequest}
            onSelect={selectCitation}
          />
        </main>
      </div>
    </div>
  );
}
