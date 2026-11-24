import type { Citation } from "@/lib/api";
import { splitAnswer } from "@/lib/citations";

interface AnswerTextProps {
  answer: string;
  citations: Citation[];
  activeChunkId: string | null;
  onSelect: (citation: Citation) => void;
}

/** Plain-text answer (never HTML) with [S1] markers rendered as evidence buttons. */
export function AnswerText({ answer, citations, activeChunkId, onSelect }: AnswerTextProps) {
  return (
    <p className="whitespace-pre-wrap leading-relaxed">
      {splitAnswer(answer, citations).map((segment, index) => {
        if (segment.kind === "text") return <span key={index}>{segment.text}</span>;
        const { citation, label } = segment;
        if (!citation) return <span key={index}>[{label}]</span>;
        const active = citation.chunk_id === activeChunkId;
        return (
          <button
            key={index}
            type="button"
            onClick={() => onSelect(citation)}
            aria-pressed={active}
            aria-label={`Show evidence ${label}: ${citation.document_name}${citation.page ? `, page ${citation.page}` : ""}`}
            className={`mx-0.5 rounded px-1 align-baseline text-xs font-semibold underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring ${
              active ? "bg-primary text-primary-foreground" : "bg-accent text-primary"
            }`}
          >
            {label}
          </button>
        );
      })}
    </p>
  );
}
