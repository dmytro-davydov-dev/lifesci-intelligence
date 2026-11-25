export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type Readiness = "checking" | "ready" | "unavailable";
export type DocumentStatus = "processing" | "ready" | "failed";
export type AnswerStatus = "answered" | "insufficient_evidence" | "clarification";

export interface DocumentSummary {
  id: string;
  name: string;
  media_type: string;
  sha256: string;
  version: string | null;
  status: DocumentStatus;
  error: string | null;
  created_at: string;
}

export interface UploadResult extends DocumentSummary {
  duplicate: boolean;
}

export interface Citation {
  label: string;
  chunk_id: string;
  document_id: string;
  document_name: string;
  page: number | null;
  section: string | null;
  quote: string;
}

export type Assessment = "supported" | "potential_gap" | "insufficient_evidence";

/** Comparison finding; `citation_labels` refer to entries of the response's `citations`. */
export interface Finding {
  topic: string;
  assessment: Assessment;
  explanation: string;
  citation_labels: string[];
}

export interface ChatResponse {
  conversation_id: string;
  answer: string;
  status: AnswerStatus;
  citations: Citation[];
  /** Comparison answers only; empty or absent for grounded Q&A. */
  findings?: Finding[];
}

export interface ChunkPassage {
  id: string;
  document_id: string;
  ordinal: number;
  page: number | null;
  section: string | null;
  text: string;
}

export interface ChatRequest {
  question: string;
  conversation_id?: string;
  document_ids?: string[];
}

/** Error carrying the API's error envelope (`{error: {code, message, request_id}}`). */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status: number,
    readonly requestId: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Fetch = typeof fetch;

async function request<T>(path: string, init: RequestInit = {}, fetchImpl: Fetch = fetch): Promise<T> {
  let response: Response;
  try {
    response = await fetchImpl(`${API_URL}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError("Cannot reach the API. Is the backend running?", "network_error", 0, null);
  }
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as T;
}

async function toApiError(response: Response): Promise<ApiError> {
  const requestId = response.headers.get("X-Request-ID");
  try {
    const body = (await response.json()) as { error?: { code?: string; message?: string; request_id?: string } };
    if (body.error?.message) {
      return new ApiError(
        body.error.message,
        body.error.code ?? "http_error",
        response.status,
        body.error.request_id ?? requestId,
      );
    }
  } catch {
    // Non-JSON error body; fall through to a generic message.
  }
  return new ApiError(`Request failed with status ${response.status}.`, "http_error", response.status, requestId);
}

/** User-facing error text including the request ID for support/debugging. */
export function formatApiError(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  return error.requestId ? `${error.message} (request ${error.requestId})` : error.message;
}

export async function fetchReadiness(signal?: AbortSignal): Promise<Readiness> {
  try {
    const response = await fetch(`${API_URL}/health/ready`, { signal, cache: "no-store" });
    return response.ok ? "ready" : "unavailable";
  } catch {
    return "unavailable";
  }
}

export function listDocuments(fetchImpl?: Fetch): Promise<DocumentSummary[]> {
  return request<DocumentSummary[]>("/api/documents", {}, fetchImpl);
}

/** `version` is optional display metadata; an existing duplicate keeps its stored version. */
export function uploadDocument(file: File, fetchImpl?: Fetch, version?: string | null): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  if (version) form.append("version", version);
  return request<UploadResult>("/api/documents", { method: "POST", body: form }, fetchImpl);
}

export function getChunk(documentId: string, chunkId: string, fetchImpl?: Fetch): Promise<ChunkPassage> {
  return request<ChunkPassage>(
    `/api/documents/${encodeURIComponent(documentId)}/chunks/${encodeURIComponent(chunkId)}`,
    {},
    fetchImpl,
  );
}

export function sendChat(body: ChatRequest, fetchImpl?: Fetch): Promise<ChatResponse> {
  return request<ChatResponse>(
    "/api/chat",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    fetchImpl,
  );
}

export function documentFileUrl(documentId: string, page?: number | null): string {
  const url = `${API_URL}/api/documents/${encodeURIComponent(documentId)}/file`;
  return page ? `${url}#page=${page}` : url;
}
