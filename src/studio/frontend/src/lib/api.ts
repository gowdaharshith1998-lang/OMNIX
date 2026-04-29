const jsonHeaders = { "Content-Type": "application/json" };

export type OpenWorkspaceResult = {
  workspace_id: string;
  mode: string;
  stats: {
    files: number;
    functions: number;
    classes: number;
    edges: number;
  };
};

export type RecentItem = {
  path: string;
  name?: string;
  last_opened_iso?: string;
};

export async function getStudioInitial(): Promise<{ path: string | null }> {
  const r = await fetch("/api/studio/initial");
  if (!r.ok) throw new Error("initial");
  return r.json() as Promise<{ path: string | null }>;
}

export async function listRecent(): Promise<RecentItem[]> {
  const r = await fetch("/api/recent");
  if (!r.ok) throw new Error("recent");
  const j = (await r.json()) as { recent: RecentItem[] };
  return j.recent;
}

export async function openWorkspace(path: string): Promise<OpenWorkspaceResult> {
  const r = await fetch("/api/workspace/open", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ path }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || "open failed");
  }
  return r.json() as Promise<OpenWorkspaceResult>;
}

export type FileEntry = {
  path: string;
  type: string;
  size: number;
  modified: number;
};

export type FileTreeNode = {
  name: string;
  type: "dir" | "file";
  size?: number;
  children?: FileTreeNode[];
};

export async function listFiles(
  workspaceId: string,
  prefix = ""
): Promise<FileEntry[]> {
  const q = new URLSearchParams();
  if (prefix) q.set("prefix", prefix);
  const r = await fetch(
    `/api/workspace/${encodeURIComponent(workspaceId)}/files?${q}`
  );
  if (!r.ok) throw new Error("list files");
  const j = (await r.json()) as { files: FileEntry[] };
  return j.files;
}

export async function getFileTree(workspaceId: string): Promise<FileTreeNode> {
  const r = await fetch(
    `/api/workspace/${encodeURIComponent(workspaceId)}/files/tree`
  );
  if (!r.ok) throw new Error("file tree");
  const j = (await r.json()) as { tree: FileTreeNode };
  return j.tree;
}

export async function createFile(
  workspaceId: string,
  path: string,
  content: string
): Promise<void> {
  const r = await fetch(
    `/api/workspace/${encodeURIComponent(workspaceId)}/file`,
    {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ path, content }),
    }
  );
  if (!r.ok) throw new Error("create file");
}

export type FileGetResult = {
  path: string;
  content: string;
  last_modified: number;
  language: string;
};

export async function getFile(
  workspaceId: string,
  path: string
): Promise<FileGetResult> {
  const q = new URLSearchParams({ path });
  const r = await fetch(
    `/api/workspace/${encodeURIComponent(workspaceId)}/file?${q}`
  );
  if (!r.ok) throw new Error("get file");
  return r.json() as Promise<FileGetResult>;
}

export class FileConflictError extends Error {
  constructor() {
    super("stale");
    this.name = "FileConflictError";
  }
}

export async function putFile(
  workspaceId: string,
  path: string,
  content: string,
  expectedLastModified: number
): Promise<{ written: boolean; new_last_modified: number }> {
  const r = await fetch(
    `/api/workspace/${encodeURIComponent(workspaceId)}/file`,
    {
      method: "PUT",
      headers: jsonHeaders,
      body: JSON.stringify({
        path,
        content,
        expected_last_modified: expectedLastModified,
      }),
    }
  );
  if (r.status === 409) throw new FileConflictError();
  if (!r.ok) throw new Error("save");
  return r.json() as Promise<{
    written: boolean;
    new_last_modified: number;
  }>;
}

export type ReceiptSource = "fabric" | "scan" | "evolution" | "studio" | "future";

export type ReceiptEntry = {
  receipt_id?: string;
  kind: string;
  target: string;
  hash_prefix: string;
  sig_alg: string;
  has_signature?: boolean;
  verified?: boolean;
  mtime_iso: string;
  source: ReceiptSource;
  path: string;
};

export async function listReceipts(
  workspaceId: string,
  opts: { since?: string; until?: string; limit?: number } = {}
): Promise<ReceiptEntry[]> {
  const q = new URLSearchParams();
  if (opts.since) q.set("since", opts.since);
  if (opts.until) q.set("until", opts.until);
  if (opts.limit) q.set("limit", String(opts.limit));
  const r = await fetch(
    `/api/workspace/${encodeURIComponent(workspaceId)}/receipts?${q}`
  );
  if (!r.ok) throw new Error("list receipts");
  const j = (await r.json()) as { receipts: ReceiptEntry[] };
  return j.receipts;
}

export async function getReceiptById(
  workspaceId: string,
  receiptId: string
): Promise<unknown> {
  const r = await fetch(
    `/api/workspace/${encodeURIComponent(workspaceId)}/receipts/${encodeURIComponent(receiptId)}`
  );
  if (!r.ok) throw new Error("get receipt");
  const j = (await r.json()) as { receipt?: unknown };
  return j.receipt ?? j;
}

export type SearchKind = "symbol" | "file" | "all";

export type SearchResult = {
  kind: "symbol" | "file";
  name: string;
  path: string;
  line: number;
  snippet: string;
};

export async function searchWorkspace(
  workspaceId: string,
  query: string,
  kind: SearchKind = "all",
  limit = 50
): Promise<SearchResult[]> {
  const q = new URLSearchParams({ q: query, kind, limit: String(limit) });
  const r = await fetch(
    `/api/workspace/${encodeURIComponent(workspaceId)}/search?${q}`
  );
  if (!r.ok) throw new Error("search");
  const j = (await r.json()) as { results: SearchResult[] };
  return j.results;
}

export type BugFailure = {
  exception_type?: string;
  exception_message?: string;
  message?: string;
  shrunk_input?: string;
  input?: string;
};

export type BugFinding = {
  file: string;
  function: string;
  lineno?: number;
  severity_score?: number;
  kind?: string;
  caller_count?: number;
  reachable_from_entries?: boolean;
  cluster_id?: string | number | null;
  failures?: BugFailure[];
  reason?: string;
  input?: string;
  language?: string;
  runner_used?: string;
  metadata?: Record<string, unknown>;
};

export type BugScanSummary = {
  findings_count?: number;
  files_scanned?: number;
  files_skipped?: number;
  import_errors_count?: number;
  timeout_skips_count?: number;
  total_examples_run?: number;
  wall_time_seconds?: number;
  skipped_main_count?: number;
  skipped_by_reason?: Record<string, number>;
};

export type BugsScanEvent =
  | {
      type: "bugs_scan_started";
      scan_id: string;
      started_at: number;
      target_path: string;
    }
  | {
      type: "bugs_scan_heartbeat";
      scan_id: string;
      elapsed_seconds: number;
    }
  | {
      type: "bugs_scan_complete";
      scan_id: string;
      findings: BugFinding[];
      summary: BugScanSummary;
      wall_time_seconds: number;
    }
  | {
      type: "bugs_scan_error";
      scan_id: string;
      error_message: string;
      error_kind: string;
    };

export class BugsScanConflictError extends Error {
  activeScanId: string;

  constructor(activeScanId: string) {
    super("Scan already in progress");
    this.name = "BugsScanConflictError";
    this.activeScanId = activeScanId;
  }
}

export async function startBugsScan(
  workspaceId: string
): Promise<{ scan_id: string }> {
  const r = await fetch(
    `/api/workspace/${encodeURIComponent(workspaceId)}/bugs/scan`,
    { method: "POST" }
  );
  if (r.status === 409) {
    const j = (await r.json().catch(() => ({}))) as { active_scan_id?: string };
    throw new BugsScanConflictError(j.active_scan_id ?? "");
  }
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || "scan failed");
  }
  return r.json() as Promise<{ scan_id: string }>;
}
