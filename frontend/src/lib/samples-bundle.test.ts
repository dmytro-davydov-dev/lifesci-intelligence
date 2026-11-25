// @vitest-environment node
import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const corpusDir = join(__dirname, "..", "..", "..", "lifesci-test-data");
const bundleDir = join(__dirname, "..", "..", "public", "samples");
const sha = (path: string) => createHash("sha256").update(readFileSync(path)).digest("hex");

describe("bundled sample documents", () => {
  it("match the corpus manifest exactly (run `npm run samples:sync` if this fails)", () => {
    const manifest = JSON.parse(readFileSync(join(corpusDir, "manifest.json"), "utf-8")) as { filename: string }[];
    const names = manifest.map((entry) => entry.filename);

    expect(readdirSync(bundleDir).sort()).toEqual([...names, "manifest.json"].sort());
    for (const name of names) {
      expect(sha(join(bundleDir, name)), name).toBe(sha(join(corpusDir, "sample-documents", name)));
    }
  });
});
