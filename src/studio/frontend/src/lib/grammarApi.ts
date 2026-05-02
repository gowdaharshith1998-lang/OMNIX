/** Grammar health + LLM budget API (localhost Studio; matches `src/studio/server.py`). */

const jsonHeaders = { "Content-Type": "application/json" };

export type GrammarRow = {
  grammar_name: string;
  files_parsed: number;
  avg_quality: number;
  parse_modes: Record<string, unknown>;
  active_patterns: number;
  recent_mutations_30d: number;
  last_evolution_receipt: string | null;
};

export type MutationRow = {
  grammar_name: string;
  action: string;
  node_type: string;
  observed_at: string;
  receipt_path: string;
  sig_path: string;
  receipt_exists: boolean;
  sig_exists: boolean;
};

export type UnknownExtensionRow = {
  ext: string;
  first_seen_at: string;
  raw_bytes_hex?: string;
};

export type LlmBudget = {
  budget_total: number | null;
  budget_remaining: number | null;
  calls_today: number | null;
  available?: boolean;
  generated_at?: string;
};

export type VerifyResult = {
  verified: boolean;
  verifier_output: string;
  receipt_path?: string;
};

async function readJson<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const t = await r.text();
      if (t) detail = t.slice(0, 500);
    } catch {
      /* ignore */
    }
    throw new Error(detail || `HTTP ${r.status}`);
  }
  return r.json() as Promise<T>;
}

export async function fetchGrammarStatus(): Promise<{ grammars: GrammarRow[] }> {
  const r = await fetch("/api/grammar/status", { cache: "no-store" });
  return readJson(r);
}

export async function fetchMutations(limit = 20): Promise<{ mutations: MutationRow[] }> {
  const q = new URLSearchParams({ limit: String(limit) });
  const r = await fetch(`/api/grammar/mutations?${q}`, { cache: "no-store" });
  return readJson(r);
}

export async function fetchUnknownExtensions(): Promise<{
  extensions: UnknownExtensionRow[];
  total: number;
}> {
  const r = await fetch("/api/grammar/unknown-extensions", { cache: "no-store" });
  return readJson(r);
}

export async function fetchLlmBudget(): Promise<LlmBudget> {
  const r = await fetch("/api/fabric/llm-budget", { cache: "no-store" });
  return readJson(r);
}

export async function verifyReceipt(receiptPath: string): Promise<VerifyResult> {
  const r = await fetch("/api/grammar/verify-receipt", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ receipt_path: receiptPath }),
  });
  const raw = await r.text();
  let j: Partial<VerifyResult> & { detail?: string } = {};
  try {
    j = JSON.parse(raw) as typeof j;
  } catch {
    if (!r.ok) throw new Error(raw.slice(0, 500) || `HTTP ${r.status}`);
  }
  if (!r.ok) {
    const msg =
      typeof j.detail === "string"
        ? j.detail
        : typeof j.verifier_output === "string"
          ? j.verifier_output
          : raw.slice(0, 500) || `HTTP ${r.status}`;
    throw new Error(msg);
  }
  return {
    verified: Boolean(j.verified),
    verifier_output: String(j.verifier_output ?? ""),
    receipt_path: j.receipt_path,
  };
}
