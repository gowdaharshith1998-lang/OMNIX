export interface ScanSummary {
  scan_id: string;
  scan_started_at: string | null;
  scan_finished_at: string | null;
  finding_count: number;
  dir_path_relative: string;
  manifest_kind?: string | null;
}

export async function fetchFindingScans(): Promise<{ scans: ScanSummary[] }> {
  const r = await fetch("/api/findings/scans");
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json() as Promise<{ scans: ScanSummary[] }>;
}

export interface VerifyScanResult {
  verified: boolean;
  reason: string;
  scan_id: string;
  finding_count: number;
  manifest_summary: Record<string, unknown>;
}

export async function verifyScan(scanId: string): Promise<VerifyScanResult> {
  const r = await fetch("/api/findings/verify-scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scan_id: scanId }),
  });
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try {
      const j = (await r.json()) as { detail?: unknown };
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return r.json() as Promise<VerifyScanResult>;
}
