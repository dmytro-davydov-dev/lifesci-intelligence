import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ChunkPassage, Citation } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getChunk: vi.fn(),
}));

const api = await import("@/lib/api");
const { EvidencePanel } = await import("@/components/evidence-panel");

const citation = (id: string): Citation => ({
  label: "S1",
  chunk_id: id,
  document_id: "d1",
  document_name: "sop.pdf",
  page: 2,
  section: null,
  quote: "q",
});
const passage = (id: string, text: string): ChunkPassage => ({ id, document_id: "d1", ordinal: 0, page: 2, section: null, text });

describe("EvidencePanel", () => {
  it("ignores a slow response for a previously selected citation", async () => {
    let resolveFirst: (value: ChunkPassage) => void = () => {};
    vi.mocked(api.getChunk)
      .mockReturnValueOnce(new Promise((resolve) => (resolveFirst = resolve)))
      .mockResolvedValueOnce(passage("c2", "Second passage"));

    const { rerender } = render(<EvidencePanel citation={citation("c1")} />);
    rerender(<EvidencePanel citation={citation("c2")} />);
    expect(await screen.findByText("Second passage")).toBeInTheDocument();

    resolveFirst(passage("c1", "Stale passage"));
    await Promise.resolve();
    expect(screen.queryByText("Stale passage")).toBeNull();
  });

  it("shows errors with request id and retries on demand", async () => {
    vi.mocked(api.getChunk)
      .mockRejectedValueOnce(new api.ApiError("Source passage not found.", "chunk_not_found", 404, "r7"))
      .mockResolvedValueOnce(passage("c1", "Recovered passage"));
    render(<EvidencePanel citation={citation("c1")} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Source passage not found. (request r7)");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Recovered passage")).toBeInTheDocument();
  });

  it("links to the original file at the cited page", async () => {
    vi.mocked(api.getChunk).mockResolvedValueOnce(passage("c1", "Text"));
    render(<EvidencePanel citation={citation("c1")} />);
    expect(screen.getByRole("link", { name: /Open original at page 2/ })).toHaveAttribute(
      "href",
      expect.stringMatching(/\/api\/documents\/d1\/file#page=2$/),
    );
  });

  it("moves focus to the heading when explicitly requested", () => {
    vi.mocked(api.getChunk).mockResolvedValue(passage("c1", "Text"));
    const { rerender } = render(<EvidencePanel citation={citation("c1")} focusRequest={0} />);
    expect(document.activeElement).not.toBe(screen.getByRole("heading", { name: "Source evidence" }));
    rerender(<EvidencePanel citation={citation("c1")} focusRequest={1} />);
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Source evidence" }));
  });

  it("lists the answer's other sources and selects one on demand", async () => {
    vi.mocked(api.getChunk).mockResolvedValue(passage("c1", "Text"));
    const second: Citation = { ...citation("c2"), label: "S2", document_name: "ref.pdf" };
    const onSelect = vi.fn();
    render(<EvidencePanel citation={citation("c1")} citations={[citation("c1"), second]} onSelect={onSelect} />);

    expect(await screen.findByTestId("evidence-passage")).toHaveTextContent("Text");
    expect(screen.getAllByTestId("evidence-passage")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "View source passage S2: ref.pdf" }));
    expect(onSelect).toHaveBeenCalledWith(second);
  });
});
