"use client";

import { useEffect, useState } from "react";

import { fetchReadiness, type Readiness } from "@/lib/api";

const LABELS: Record<Readiness, string> = {
  checking: "Checking API…",
  ready: "API and database ready",
  unavailable: "API unavailable",
};

export function ApiStatus() {
  const [status, setStatus] = useState<Readiness>("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetchReadiness(controller.signal).then((result) => {
      if (!controller.signal.aborted) setStatus(result);
    });
    return () => controller.abort();
  }, []);

  return (
    <p role="status" aria-live="polite" data-status={status} className="text-sm">
      {LABELS[status]}
    </p>
  );
}
