// Copies manifest-listed sample documents from ../lifesci-test-data into public/samples/
// so the frontend can serve them (and offer one-click loading) wherever it is deployed.
// Only sample-documents/ is copied; evals/ and adversarial-documents/ never are.
//
//   npm run samples:sync
import { copyFileSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = dirname(dirname(fileURLToPath(import.meta.url)));
const corpusDir = join(frontendDir, "..", "lifesci-test-data");
const targetDir = join(frontendDir, "public", "samples");

const manifest = JSON.parse(readFileSync(join(corpusDir, "manifest.json"), "utf-8"));
const entries = manifest.map(({ filename, document_id, version }) => {
  if (typeof filename !== "string" || !filename || basename(filename) !== filename) {
    throw new Error(`Manifest filename must be a bare file name: ${JSON.stringify(filename)}`);
  }
  return { filename, document_id: document_id ?? filename, version: version ?? null };
});

mkdirSync(targetDir, { recursive: true });
for (const stale of readdirSync(targetDir)) rmSync(join(targetDir, stale));
for (const { filename } of entries) {
  copyFileSync(join(corpusDir, "sample-documents", filename), join(targetDir, filename));
}
writeFileSync(join(targetDir, "manifest.json"), `${JSON.stringify(entries, null, 2)}\n`);
console.log(`Synced ${entries.length} sample documents to public/samples/`);
