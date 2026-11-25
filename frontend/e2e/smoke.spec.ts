import path from "node:path";

import { expect, type Page, test } from "@playwright/test";

// Project-relative corpus path: works locally and in CI checkouts.
const SAMPLE_DIR = path.resolve(__dirname, "../../lifesci-test-data/sample-documents");
const SOP = path.join(SAMPLE_DIR, "SOP-001-v2.pdf");
const REFERENCE = path.join(SAMPLE_DIR, "QMS-REF-001.pdf");
const COMPARISON = "Compare reporting deadlines in current SOP-001 and QMS-REF-001."; // golden E06
const ANSWERABLE = "How soon must a deviation be recorded under the current SOP-001?"; // golden E01
const UNANSWERABLE = "What is the approved storage temperature for product NB-42?"; // golden E12
const SCREENSHOT_DIR = process.env.E2E_SCREENSHOT_DIR; // optional output directory for docs

function trackPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

async function uploadSop(page: Page) {
  await page.setInputFiles("#document-upload", SOP);
  await expect(page.getByText(/SOP-001-v2\.pdf (is ready|was already uploaded)\./)).toBeVisible();
}

async function ask(page: Page, question: string) {
  const answers = page.getByRole("article", { name: "Assistant answer" });
  const before = await answers.count();
  await page.getByLabel("Question", { exact: true }).fill(question);
  await page.getByLabel("Question", { exact: true }).press("Enter");
  await expect(answers).toHaveCount(before + 1);
  return answers.last();
}

test("upload, ask, inspect evidence, abstain and detect duplicates", async ({ page }) => {
  const errors = trackPageErrors(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "LifeSci Intelligence" })).toBeVisible();
  await expect(page.locator('[data-status="ready"]')).toHaveText("API and database ready");

  await uploadSop(page);
  await page.getByRole("checkbox", { name: /SOP-001-v2\.pdf/ }).check();
  await expect(page.getByText("Asking 1 selected document")).toBeVisible();

  const answer = await ask(page, ANSWERABLE);
  const citation = answer.getByRole("button", { name: /^Show evidence S1: SOP-001-v2\.pdf, page \d+$/ });
  await expect(citation).toBeVisible();
  await citation.click();
  await expect(citation).toHaveAttribute("aria-pressed", "true");

  const passage = page.getByTestId("evidence-passage");
  await expect(passage).toContainText("SOP-001-v2");
  const original = page.getByRole("link", { name: /Open original at page \d+/ });
  const href = await original.getAttribute("href");
  expect(href).toMatch(/\/api\/documents\/[0-9a-f-]+\/file#page=\d+$/);

  const file = await page.request.get(href!.split("#")[0]);
  expect(file.status()).toBe(200);
  expect(file.headers()["content-type"]).toBe("application/pdf");
  expect(file.headers()["content-disposition"]).toMatch(/^inline/);
  // PDFs must not get CSP `sandbox` (used for text files): it blocks the browser PDF viewer.
  expect(file.headers()["content-security-policy"] ?? "").not.toContain("sandbox");

  if (SCREENSHOT_DIR) await page.screenshot({ path: path.join(SCREENSHOT_DIR, "workspace-qa.png"), fullPage: true });

  const abstention = await ask(page, UNANSWERABLE);
  await expect(abstention.getByText("Insufficient evidence")).toBeVisible();
  await expect(abstention.getByRole("button", { name: /Show evidence/ })).toHaveCount(0);

  await page.setInputFiles("#document-upload", SOP);
  await expect(page.getByText("SOP-001-v2.pdf was already uploaded.")).toBeVisible();

  expect(errors).toEqual([]);
});

test("compares two selected documents with structured findings", async ({ page }) => {
  const errors = trackPageErrors(page);
  await page.goto("/");
  await uploadSop(page);
  await page.setInputFiles("#document-upload", REFERENCE);
  await expect(page.getByText(/QMS-REF-001\.pdf (is ready|was already uploaded)\./)).toBeVisible();
  await page.getByRole("checkbox", { name: /SOP-001-v2\.pdf/ }).check();
  await page.getByRole("checkbox", { name: /QMS-REF-001\.pdf/ }).check();
  await expect(page.getByText("Asking 2 selected documents")).toBeVisible();

  const answer = await ask(page, COMPARISON);
  const findings = answer.getByRole("region", { name: "Comparison findings" });
  await expect(findings).toBeVisible();
  await expect(findings.getByText(/Supported|Potential gap|Insufficient evidence/).first()).toBeVisible();
  const sources = answer.getByRole("list", { name: "Sources" });
  await expect(sources.getByRole("button", { name: /SOP-001-v2\.pdf/ })).toBeVisible();
  await expect(sources.getByRole("button", { name: /QMS-REF-001\.pdf/ })).toBeVisible();
  await sources.getByRole("button", { name: /QMS-REF-001\.pdf/ }).click();
  await expect(page.getByTestId("evidence-passage")).toContainText("QMS-REF-001");
  if (SCREENSHOT_DIR) {
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "workspace-comparison.png"), fullPage: true });
  }

  expect(errors).toEqual([]);
});

test("rejects a non-PDF renamed to .pdf with an actionable error", async ({ page }) => {
  await page.goto("/");
  await page.setInputFiles("#document-upload", {
    name: "not-really.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("plain text pretending to be a PDF"),
  });
  // Scope to the documents panel: Next.js renders its own role="alert" route announcer.
  const alert = page.getByRole("region", { name: "Document collection" }).getByRole("alert");
  await expect(alert).toContainText("File has a .pdf extension but is not a PDF.");
  await expect(alert).toContainText(/\(request [0-9a-f]+\)/);
});

test("small screens stack panels without horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator('[data-status="ready"]')).toHaveText("API and database ready");
  await expect(page.getByRole("checkbox").first()).toBeVisible(); // measure with documents listed
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("loads the bundled sample documents with one click", async ({ page }) => {
  const errors = trackPageErrors(page);
  await page.goto("/");

  const manifest = await (await page.request.get("/samples/manifest.json")).json();
  expect(manifest).toHaveLength(7);

  await page.getByRole("button", { name: "Load sample documents" }).click();
  // Counts depend on what is already in the database; there must be no failures.
  await expect(page.getByRole("status").filter({ hasText: /^Sample documents: \d+ added, \d+ already present\.$/ })).toBeVisible({
    timeout: 45_000,
  });
  for (const { filename } of manifest as { filename: string }[]) {
    await expect(page.getByTitle(filename, { exact: true })).toBeVisible();
  }
  expect(errors).toEqual([]);
});
