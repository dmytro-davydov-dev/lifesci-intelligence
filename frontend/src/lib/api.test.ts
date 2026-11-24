import { describe, expect, it, vi } from "vitest";

import { ApiError, documentFileUrl, listDocuments, sendChat } from "@/lib/api";

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("api client", () => {
  it("posts chat requests as JSON and returns the parsed body", async () => {
    const body = { conversation_id: "c1", answer: "a", status: "answered", citations: [] };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(body));

    const result = await sendChat({ question: "Q?", document_ids: ["d1"] }, fetchMock);

    expect(result).toEqual(body);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/chat$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ question: "Q?", document_ids: ["d1"] });
  });

  it("raises ApiError with the server error envelope", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ error: { code: "invalid_document_scope", message: "Unknown ids", request_id: "r1" } }, 422),
    );

    const error = await listDocuments(fetchMock).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "invalid_document_scope", message: "Unknown ids", status: 422, requestId: "r1" });
  });

  it("falls back to a generic error for non-JSON failures", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("oops", { status: 502, headers: { "X-Request-ID": "r2" } }));
    await expect(listDocuments(fetchMock)).rejects.toMatchObject({ status: 502, requestId: "r2", code: "http_error" });
  });

  it("reports network failures clearly", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(listDocuments(fetchMock)).rejects.toMatchObject({ code: "network_error", status: 0 });
  });

  it("builds file URLs with an optional page anchor and encoded ids", () => {
    expect(documentFileUrl("a/b", 3)).toMatch(/\/api\/documents\/a%2Fb\/file#page=3$/);
    expect(documentFileUrl("d1")).toMatch(/\/api\/documents\/d1\/file$/);
  });
});
