import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { type ChatTurn, ChatPanel } from "@/components/chat-panel";
import type { Citation } from "@/lib/api";

function citation(label: string, document_name: string): Citation {
  return {
    label,
    chunk_id: `chunk-${label}`,
    document_id: `doc-${label}`,
    document_name,
    page: 1,
    section: null,
    quote: "quote",
  };
}

function renderPanel(overrides: Partial<Parameters<typeof ChatPanel>[0]> = {}) {
  const props = {
    turns: [] as ChatTurn[],
    pending: false,
    error: null,
    canAsk: true,
    activeChunkId: null,
    onAsk: vi.fn().mockResolvedValue(true),
    onSelectCitation: vi.fn(),
    onNewConversation: vi.fn(),
    ...overrides,
  };
  render(<ChatPanel {...props} />);
  return props;
}

describe("ChatPanel", () => {
  it("submits a trimmed question with Enter and clears the input", async () => {
    const props = renderPanel();
    const input = screen.getByLabelText("Question");

    await userEvent.type(input, "  When are deviations reported?  {Enter}");

    expect(props.onAsk).toHaveBeenCalledWith("When are deviations reported?");
    expect(input).toHaveValue("");
  });

  it("restores the question when asking fails", async () => {
    renderPanel({ onAsk: vi.fn().mockResolvedValue(false) });
    const input = screen.getByLabelText("Question");

    await userEvent.type(input, "When?{Enter}");

    expect(input).toHaveValue("When?");
  });

  it("does not submit blank questions", async () => {
    const props = renderPanel();
    await userEvent.type(screen.getByLabelText("Question"), "   {Enter}");
    expect(props.onAsk).not.toHaveBeenCalled();
  });

  it("sends example prompts", async () => {
    const props = renderPanel();
    await userEvent.click(screen.getByRole("button", { name: /deviation be reported/ }));
    expect(props.onAsk).toHaveBeenCalledWith("Within how many hours must a deviation be reported?");
  });

  it("disables asking until a document is ready", () => {
    renderPanel({ canAsk: false });
    expect(screen.getByLabelText("Question")).toBeDisabled();
    expect(screen.getByText("Upload a document to enable questions.")).toBeInTheDocument();
  });

  it("labels abstentions and shows errors", () => {
    renderPanel({
      turns: [{ id: "1", role: "assistant", content: "Not enough evidence.", status: "insufficient_evidence", citations: [] }],
      error: "Model request failed (request abc)",
    });
    expect(screen.getAllByText(/Insufficient evidence/)[0]).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Insufficient evidence.");
    expect(screen.getByRole("alert")).toHaveTextContent("request abc");
  });

  it("shows a loading state while pending", () => {
    renderPanel({ pending: true });
    expect(screen.getByRole("status")).toHaveTextContent("Searching documents");
    expect(screen.getByRole("button", { name: "Send question" })).toBeDisabled();
  });

  it("renders comparison findings with assessments and clickable evidence", async () => {
    const sop = citation("S1", "SOP-001.pdf");
    const reference = citation("S2", "QMS-REF-001.pdf");
    const props = renderPanel({
      turns: [
        {
          id: "1",
          role: "assistant",
          content: "The SOP allows longer [S1].",
          status: "answered",
          citations: [sop, reference],
          findings: [
            {
              topic: "Reporting deadline",
              assessment: "potential_gap",
              explanation: "48 hours [S1] versus 24 hours [S2].",
              citation_labels: ["S1", "S2"],
            },
            { topic: "Closure", assessment: "insufficient_evidence", explanation: "Not covered.", citation_labels: [] },
          ],
        },
      ],
    });

    const findings = screen.getByRole("region", { name: "Comparison findings" });
    expect(findings).toHaveTextContent("Potential gap");
    expect(findings).toHaveTextContent("Reporting deadline");
    expect(findings).toHaveTextContent("Insufficient evidence");
    expect(findings).toHaveTextContent("not a compliance determination");

    await userEvent.click(screen.getByRole("button", { name: "Show evidence S2: QMS-REF-001.pdf, page 1" }));
    expect(props.onSelectCitation).toHaveBeenCalledWith(reference);
  });

  it("shows no findings section for plain answers", () => {
    renderPanel({
      turns: [{ id: "1", role: "assistant", content: "48 hours [S1].", status: "answered", citations: [citation("S1", "a.pdf")] }],
    });
    expect(screen.queryByRole("region", { name: "Comparison findings" })).not.toBeInTheDocument();
  });
});
