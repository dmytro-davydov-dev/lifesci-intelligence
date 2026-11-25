import { describe, expect, it, vi } from "vitest";

import { ApiError, type UploadResult } from "@/lib/api";
import { loadSampleDocuments } from "@/lib/samples";

const uploaded = (overrides: Partial<UploadResult>): UploadResult => ({
  id: "d1",
  name: "x",
  media_type: "application/pdf",
  sha256: "x",
  version: null,
  status: "ready",
  error: null,
  created_at: "2026-11-25T00:00:00Z",
  duplicate: false,
  ...overrides,
});

function fakeSite(files: Record<string, string | null>) {
  const manifest = Object.keys(files).map((filename, i) => ({
    filename,
    document_id: filename,
    version: i === 0 ? "2.0" : null,
  }));
  return vi.fn(async (url: string) => {
    if (url === "/samples/manifest.json") return Response.json(manifest);
    const body = files[decodeURIComponent(url.replace("/samples/", ""))];
    return body == null ? new Response("missing", { status: 404 }) : new Response(body);
  }) as unknown as typeof fetch;
}

describe("loadSampleDocuments", () => {
  it("uploads every bundled sample under its own file name and tallies outcomes", async () => {
    const fetchImpl = fakeSite({ "A.pdf": "%PDF-a", "B.pdf": "%PDF-b", "C.txt": "c", "D.pdf": null });
    const upload = vi
      .fn()
      .mockResolvedValueOnce(uploaded({}))
      .mockResolvedValueOnce(uploaded({ duplicate: true }))
      .mockResolvedValueOnce(uploaded({ status: "failed", error: "boom" }));

    const summary = await loadSampleDocuments(fetchImpl, upload);

    expect(upload.mock.calls.map(([file, version]) => [(file as File).name, version])).toEqual([
      ["A.pdf", "2.0"],
      ["B.pdf", null],
      ["C.txt", null],
    ]);
    expect(await (upload.mock.calls[0][0] as File).text()).toBe("%PDF-a");
    expect(summary).toEqual({ created: 1, duplicate: 1, failed: ["C.txt", "D.pdf"] });
  });

  it("reports a missing bundle instead of uploading anything", async () => {
    const fetchImpl = vi.fn(async () => new Response("", { status: 404 })) as unknown as typeof fetch;
    const upload = vi.fn();

    await expect(loadSampleDocuments(fetchImpl, upload)).rejects.toBeInstanceOf(ApiError);
    expect(upload).not.toHaveBeenCalled();
  });
});
