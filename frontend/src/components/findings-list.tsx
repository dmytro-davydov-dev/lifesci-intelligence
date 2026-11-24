import { AnswerText } from "@/components/answer-text";
import { Badge } from "@/components/ui/badge";
import type { Assessment, Citation, Finding } from "@/lib/api";

const ASSESSMENT: Record<Assessment, { label: string; variant: "default" | "destructive" | "outline" }> = {
  supported: { label: "Supported", variant: "default" },
  potential_gap: { label: "Potential gap", variant: "destructive" },
  insufficient_evidence: { label: "Insufficient evidence", variant: "outline" },
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
    <section aria-label="Comparison findings" className="flex flex-col gap-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Findings</h3>
      <ul className="flex flex-col gap-2">
        {findings.map((finding, index) => {
          const assessment = ASSESSMENT[finding.assessment];
          return (
            <li key={index} className="flex flex-col gap-1 rounded-md border p-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={assessment.variant}>{assessment.label}</Badge>
                <span className="font-medium">{finding.topic}</span>
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
      </ul>
      <p className="text-xs text-muted-foreground">
        Potential gaps are for human review, not a compliance determination.
      </p>
    </section>
  );
}
