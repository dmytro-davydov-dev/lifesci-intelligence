import { AnswerText } from "@/components/answer-text";
import { Badge } from "@/components/ui/badge";
import type { Assessment, Citation, Finding } from "@/lib/api";

const ASSESSMENT: Record<Assessment, { label: string; className: string }> = {
  supported: { label: "Supported", className: "bg-accent text-accent-foreground" },
  potential_gap: { label: "Potential gap", className: "border-warning/40 bg-warning/10 text-warning" },
  insufficient_evidence: { label: "Insufficient evidence", className: "border-border text-muted-foreground" },
};

interface FindingsListProps {
  findings: Finding[];
  citations: Citation[];
  activeChunkId: string | null;
  onSelect: (citation: Citation) => void;
}

/** Structured comparison findings; explanations are plain text with clickable [S1] markers. */
export function FindingsList({ findings, citations, activeChunkId, onSelect }: FindingsListProps) {
  return (
    <section aria-label="Comparison findings" className="flex flex-col gap-3">
      <h3 className="sr-only">Findings</h3>
      <ol className="flex flex-col gap-3">
        {findings.map((finding, index) => {
          const assessment = ASSESSMENT[finding.assessment];
          return (
            <li key={index} className="flex flex-col gap-1.5 rounded-lg border bg-muted px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold">
                  {index + 1}. {finding.topic}
                </span>
                <Badge variant="outline" className={assessment.className}>
                  {assessment.label}
                </Badge>
              </div>
              <AnswerText
                answer={finding.explanation}
                citations={citations}
                activeChunkId={activeChunkId}
                onSelect={onSelect}
              />
            </li>
          );
        })}
      </ol>
      <p className="text-xs text-muted-foreground">
        Potential gaps are for human review, not a compliance determination.
      </p>
    </section>
  );
}
