import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { UploadResult } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  uploadDocument: vi.fn(),
}));

const api = await import("@/lib/api");
const { DocumentPanel } = await import("@/components/document-panel");

const result = (overrides: Partial<UploadResult>): UploadResult => ({
  id: "d1",
  name: "sop.pdf",
  media_type: "application/pdf",
  sha256: "x",
  version: null,
  status: "ready",
  error: null,
  created_at: "2026-11-24T00:00:00Z",
  duplicate: false,
  ...overrides,
});

function renderPanel() {
  const onUploaded = vi.fn();
  const { container } = render(
    <DocumentPanel
      documents={[]}
      loading={false}
      loadError={null}
      selectedIds={new Set()}
      onToggle={() => {}}
      onUploaded={onUploaded}
      onRefresh={() => {}}
    />,
  );
  const input = container.querySelector<HTMLInputElement>("#document-upload")!;
  return { input, onUploaded };
}

const file = new File(["%PDF-1.7"], "sop.pdf", { type: "application/pdf" });

describe("DocumentPanel", () => {
  it.each([
    [result({}), "sop.pdf is ready."],
    [result({ duplicate: true }), "sop.pdf was already uploaded."],
    [result({ status: "failed", error: "Embedding request failed" }), "sop.pdf: Embedding request failed"],
  ])("reports upload outcome %#", async (uploaded, message) => {
    vi.mocked(api.uploadDocument).mockResolvedValueOnce(uploaded);
    const { input, onUploaded } = renderPanel();

    await userEvent.upload(input, file);

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(onUploaded).toHaveBeenCalled();
  });

  it("shows API validation errors with request id", async () => {
    vi.mocked(api.uploadDocument).mockRejectedValueOnce(
      new api.ApiError("The PDF is password-protected.", "encrypted_pdf", 422, "r3"),
    );
    const { input } = renderPanel();

    await userEvent.upload(input, file);

    expect(await screen.findByRole("alert")).toHaveTextContent("The PDF is password-protected. (request r3)");
  });

  it("shows an empty state and keeps the hidden file input out of the tab order", () => {
    const { input } = renderPanel();
    expect(screen.getByText(/No documents yet/)).toBeInTheDocument();
    expect(input).toHaveAttribute("tabindex", "-1");
  });
});
