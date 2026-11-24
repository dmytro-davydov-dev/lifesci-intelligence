import type { Citation } from "@/lib/api";

export type AnswerSegment =
  | { kind: "text"; text: string }
  | { kind: "citation"; label: string; citation: Citation | undefined };

const MARKER_GROUP = /\[\s*[Ss]\d+(?:\s*,\s*[Ss]\d+)*\s*\]/g;

/** Split answer text into plain text and citation markers ([S1] or [S1, S2]). */
export function splitAnswer(answer: string, citations: Citation[]): AnswerSegment[] {
  const byLabel = new Map(citations.map((c) => [c.label.toUpperCase(), c]));
  const segments: AnswerSegment[] = [];
  let last = 0;
  for (const match of answer.matchAll(MARKER_GROUP)) {
    const start = match.index ?? 0;
    if (start > last) segments.push({ kind: "text", text: answer.slice(last, start) });
    for (const raw of match[0].match(/[Ss]\d+/g) ?? []) {
      const label = raw.toUpperCase();
      segments.push({ kind: "citation", label, citation: byLabel.get(label) });
    }
    last = start + match[0].length;
  }
  if (last < answer.length) segments.push({ kind: "text", text: answer.slice(last) });
  return segments;
}

export function describeLocation(citation: Pick<Citation, "document_name" | "page" | "section">): string {
  const parts = [citation.document_name];
  if (citation.page) parts.push(`p. ${citation.page}`);
  if (citation.section) parts.push(citation.section);
  return parts.join(" · ");
}
