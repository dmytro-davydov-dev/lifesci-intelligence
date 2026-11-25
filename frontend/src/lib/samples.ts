import { ApiError, type UploadResult, uploadDocument } from "@/lib/api";

/** Synthetic sample corpus bundled with the frontend (see scripts/sync-samples.mjs). */
export const SAMPLES_PATH = "/samples";

interface SampleEntry {
  filename: string;
  document_id: string;
  version: string | null;
}

export interface SampleLoadSummary {
  created: number;
  duplicate: number;
  failed: string[];
}

type Fetch = typeof fetch;
type Upload = (file: File, version: string | null) => Promise<UploadResult>;

/** Fetches each bundled sample from this site and uploads it through the API, one at a time. */
export async function loadSampleDocuments(
  fetchImpl: Fetch = fetch,
  upload: Upload = (file, version) => uploadDocument(file, undefined, version),
): Promise<SampleLoadSummary> {
  const entries = await fetchManifest(fetchImpl);
  const summary: SampleLoadSummary = { created: 0, duplicate: 0, failed: [] };
  for (const { filename, version } of entries) {
    const response = await fetchImpl(`${SAMPLES_PATH}/${encodeURIComponent(filename)}`);
    if (!response.ok) {
      summary.failed.push(filename);
      continue;
    }
    const blob = await response.blob();
    const result = await upload(new File([blob], filename, { type: blob.type }), version);
    if (result.status === "failed") summary.failed.push(filename);
    else if (result.duplicate) summary.duplicate += 1;
    else summary.created += 1;
  }
  return summary;
}

async function fetchManifest(fetchImpl: Fetch): Promise<SampleEntry[]> {
  let response: Response;
  try {
    response = await fetchImpl(`${SAMPLES_PATH}/manifest.json`);
  } catch {
    throw new ApiError("Sample documents could not be fetched.", "samples_unavailable", 0, null);
  }
  if (!response.ok) {
    throw new ApiError("Sample documents are not bundled with this build.", "samples_unavailable", response.status, null);
  }
  return (await response.json()) as SampleEntry[];
}
