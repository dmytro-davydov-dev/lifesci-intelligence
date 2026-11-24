export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type Readiness = "checking" | "ready" | "unavailable";

export async function fetchReadiness(signal?: AbortSignal): Promise<Readiness> {
  try {
    const response = await fetch(`${API_URL}/health/ready`, { signal, cache: "no-store" });
    return response.ok ? "ready" : "unavailable";
  } catch {
    return "unavailable";
  }
}
