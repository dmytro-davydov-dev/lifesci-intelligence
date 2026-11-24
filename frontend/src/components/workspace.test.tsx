import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatResponse, DocumentSummary } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchReadiness: vi.fn().mockResolvedValue("ready"),
    listDocuments: vi.fn(),
    sendChat: vi.fn(),
    getChunk: vi.fn().mockResolvedValue({ id: "c1", document_id: "d1", ordinal: 0, page: 2, section: null, text: "Passage" }),
  };
});

const api = await import("@/lib/api");
const { Workspace } = await import("@/components/workspace");

const doc = (id: string, status: DocumentSummary["status"] = "ready"): DocumentSummary => ({
  id,
  name: `${id}.pdf`,
  media_type: "application/pdf",
  sha256: id,
  version: null,
  status,
  error: null,
  created_at: "2026-11-24T00:00:00Z",
});

const answer = (conversation_id = "conv-1"): ChatResponse => ({
  conversation_id,
  answer: "Within 24 hours [S1].",
  status: "answered",
  citations: [
    { label: "S1", chunk_id: "c1", document_id: "d1", document_name: "d1.pdf", page: 2, section: null, quote: "q" },
  ],
});

async function ask(question: string) {
  await userEvent.type(screen.getByLabelText("Question"), `${question}{Enter}`);
}

describe("Workspace", () => {
  beforeEach(() => {
    vi.mocked(api.listDocuments).mockReset().mockResolvedValue([doc("d1"), doc("d2")]);
    vi.mocked(api.sendChat).mockReset();
  });

  it("omits document_ids until documents are selected and reuses the conversation id", async () => {
    vi.mocked(api.sendChat).mockResolvedValue(answer());
    render(<Workspace />);
    await screen.findByText("d1.pdf");

    await ask("First?");
    await screen.findByText(/Within 24 hours/);
    expect(vi.mocked(api.sendChat).mock.calls[0][0]).toEqual({
      question: "First?",
      conversation_id: undefined,
      document_ids: undefined,
    });

    await userEvent.click(screen.getByRole("checkbox", { name: /d2\.pdf/ }));
    await ask("Second?");
    await waitFor(() => expect(api.sendChat).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.sendChat).mock.calls[1][0]).toEqual({
      question: "Second?",
      conversation_id: "conv-1",
      document_ids: ["d2"],
    });
  });

  it("removes the unanswered turn, restores the question and shows the request id on failure", async () => {
    vi.mocked(api.sendChat).mockRejectedValue(new api.ApiError("Model unavailable", "model_unavailable", 503, "req-9"));
    render(<Workspace />);
    await screen.findByText("d1.pdf");

    await ask("When?");

    expect(await screen.findByRole("alert")).toHaveTextContent("Model unavailable (request req-9)");
    expect(screen.getByLabelText("Question")).toHaveValue("When?");
    expect(screen.queryByText("You asked:")).toBeNull();
  });

  it("starts a new conversation when the server no longer knows it", async () => {
    vi.mocked(api.sendChat)
      .mockResolvedValueOnce(answer("gone"))
      .mockRejectedValueOnce(new api.ApiError("Conversation not found.", "conversation_not_found", 404, null))
      .mockResolvedValueOnce(answer("fresh"));
    render(<Workspace />);
    await screen.findByText("d1.pdf");

    await ask("One?");
    await screen.findByText(/Within 24 hours/);
    await ask("Two?");
    await screen.findByText(/no longer available/);
    await userEvent.click(screen.getByRole("button", { name: "Send question" }));

    await waitFor(() => expect(api.sendChat).toHaveBeenCalledTimes(3));
    expect(vi.mocked(api.sendChat).mock.calls[2][0].conversation_id).toBeUndefined();
  });

  it("prunes selections when a document is no longer ready", async () => {
    render(<Workspace />);
    await userEvent.click(await screen.findByRole("checkbox", { name: /d1\.pdf/ }));
    expect(screen.getByText("Asking 1 selected document")).toBeInTheDocument();

    vi.mocked(api.listDocuments).mockResolvedValue([doc("d1", "failed"), doc("d2")]);
    await userEvent.click(screen.getByRole("button", { name: "Refresh documents" }));

    await screen.findByText("Asking all 1 ready document");
    expect(screen.getByRole("checkbox", { name: /d1\.pdf/ })).not.toBeChecked();
  });
});
