import { describe, expect, it } from "vitest";

import type { Citation } from "@/lib/api";
import { describeLocation, splitAnswer } from "@/lib/citations";

const citation = (label: string, page: number | null = 2): Citation => ({
  label,
  chunk_id: `chunk-${label}`,
  document_id: "doc-1",
  document_name: "sop.pdf",
  page,
  section: "4.2 Reporting",
  quote: "q",
});

describe("splitAnswer", () => {
  it("splits text and single markers", () => {
    const s1 = citation("S1");
    expect(splitAnswer("Within 24 hours [S1].", [s1])).toEqual([
      { kind: "text", text: "Within 24 hours " },
      { kind: "citation", label: "S1", citation: s1 },
      { kind: "text", text: "." },
    ]);
  });

  it("expands grouped and lowercase markers", () => {
    const [s1, s2] = [citation("S1"), citation("S2")];
    const labels = splitAnswer("A [s1, S2]", [s1, s2])
      .filter((segment) => segment.kind === "citation")
      .map((segment) => segment.kind === "citation" && segment.citation);
    expect(labels).toEqual([s1, s2]);
  });

  it("keeps unknown markers without a citation", () => {
    expect(splitAnswer("[S9]", [])).toEqual([{ kind: "citation", label: "S9", citation: undefined }]);
  });

  it("returns plain text unchanged when there are no markers", () => {
    expect(splitAnswer("No evidence.", [])).toEqual([{ kind: "text", text: "No evidence." }]);
  });
});

describe("describeLocation", () => {
  it("joins document, page and section", () => {
    expect(describeLocation(citation("S1"))).toBe("sop.pdf · p. 2 · 4.2 Reporting");
  });

  it("omits missing page", () => {
    expect(describeLocation({ document_name: "notes.md", page: null, section: null })).toBe("notes.md");
  });
});
