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
