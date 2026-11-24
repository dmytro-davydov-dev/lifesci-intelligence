import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AnswerText } from "@/components/answer-text";
import type { Citation } from "@/lib/api";

const s1: Citation = {
  label: "S1",
  chunk_id: "chunk-1",
  document_id: "doc-1",
  document_name: "sop.pdf",
  page: 2,
  section: null,
  quote: "q",
};

describe("AnswerText", () => {
  it("renders citation markers as accessible buttons that select evidence", async () => {
    const onSelect = vi.fn();
    render(<AnswerText answer="Within 24 hours [S1]." citations={[s1]} activeChunkId={null} onSelect={onSelect} />);

    const button = screen.getByRole("button", { name: "Show evidence S1: sop.pdf, page 2" });
    await userEvent.click(button);

    expect(onSelect).toHaveBeenCalledWith(s1);
    expect(button).toHaveAttribute("aria-pressed", "false");
  });

  it("marks the active citation as pressed", () => {
    render(<AnswerText answer="[S1]" citations={[s1]} activeChunkId="chunk-1" onSelect={() => {}} />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });

  it("renders model output as text, never as HTML", () => {
    const { container } = render(
      <AnswerText answer={'<img src=x onerror="alert(1)"> **bold** [S1]'} citations={[s1]} activeChunkId={null} onSelect={() => {}} />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror="alert(1)"> **bold**');
  });

  it("shows unknown markers as plain text", () => {
    render(<AnswerText answer="Claim [S9]" citations={[]} activeChunkId={null} onSelect={() => {}} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("[S9]")).toBeInTheDocument();
  });
});
