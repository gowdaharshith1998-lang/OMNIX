/**
 * Client for /v1/cutover/{unit}/{state,preview,shift,rollback} on the
 * Shape A FastAPI orchestrator. Mirrors the api.ts convention of using
 * plain fetch (the cloud API gates auth at the gateway).
 */

const jsonHeaders = { "Content-Type": "application/json" };

export interface CutoverHistoryEntry {
  ts: number;
  fromPct: number;
  toPct: number;
  receiptId: string;
  receiptUrl: string;
  operator: string;
}

export interface CutoverState {
  unit: string;
  currentPct: number;
  history: CutoverHistoryEntry[];
  pendingShift?: { toPct: number; receiptPreview: ReceiptPreview };
}

/**
 * The receipt preview shape — kept structurally typed because the cloud
 * returns the canonical Shape A payload verbatim and we render it in a
 * <pre> block. Signature bytes arrive base64-encoded.
 */
export interface ReceiptPreview {
  unit_id: string;
  tenant_id: string;
  previous_percentage: number;
  target_percentage: number;
  verifier_summary: Record<string, unknown>;
  created_at_unix: number;
  kind: string;
  signature_b64?: string;
  public_key_b64?: string;
}

export const SNAP_POINTS = [0, 1, 5, 10, 25, 50, 75, 100] as const;
export type SnapPoint = (typeof SNAP_POINTS)[number];

async function callCutover<T>(
  path: string,
  init?: RequestInit & { body?: BodyInit }
): Promise<T> {
  const r = await fetch(`/v1/cutover/${path}`, init);
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`cutover ${path} failed (${r.status}): ${text}`);
  }
  return r.json() as Promise<T>;
}

export async function getCutoverState(unit: string): Promise<CutoverState> {
  return callCutover<CutoverState>(`${encodeURIComponent(unit)}/state`);
}

export async function previewShift(
  unit: string,
  toPct: number
): Promise<{ receiptPreview: ReceiptPreview }> {
  return callCutover<{ receiptPreview: ReceiptPreview }>(
    `${encodeURIComponent(unit)}/preview`,
    {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ to_pct: toPct }),
    }
  );
}

export async function confirmShift(
  unit: string,
  toPct: number,
  signedReceipt: ReceiptPreview
): Promise<{ receiptId: string }> {
  return callCutover<{ receiptId: string }>(
    `${encodeURIComponent(unit)}/shift`,
    {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ to_pct: toPct, signed_receipt: signedReceipt }),
    }
  );
}

export async function rollback(
  unit: string,
  reason: string
): Promise<{ receiptId: string }> {
  return callCutover<{ receiptId: string }>(
    `${encodeURIComponent(unit)}/rollback`,
    {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ reason }),
    }
  );
}

/** snap an arbitrary 0-100 slider value to the nearest snap point */
export function snapTo(value: number): SnapPoint {
  let best: SnapPoint = SNAP_POINTS[0];
  let bestDelta = Math.abs(value - best);
  for (const point of SNAP_POINTS) {
    const delta = Math.abs(value - point);
    if (delta < bestDelta) {
      best = point;
      bestDelta = delta;
    }
  }
  return best;
}
