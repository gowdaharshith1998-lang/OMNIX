import { useEffect, useState } from "react";
import { getFileTree, type FileTreeNode } from "@/lib/api";

type Props = {
  workspaceId: string;
  onOpenFile: (path: string) => void;
};

function formatSize(size: number | undefined) {
  if (!size) return "";
  if (size < 1024) return `${size}b`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)}kb`;
  return `${(size / (1024 * 1024)).toFixed(1)}mb`;
}

function TreeNode({
  node,
  path,
  onOpenFile,
}: {
  node: FileTreeNode;
  path: string;
  onOpenFile: (path: string) => void;
}) {
  const fullPath = path ? `${path}/${node.name}` : node.name;
  if (node.type === "file") {
    return (
      <li>
        <button
          type="button"
          className="flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left font-mono text-[11px] text-omnix-text-muted hover:bg-[rgba(99,102,241,0.08)] hover:text-omnix-text-primary"
          onClick={() => onOpenFile(fullPath)}
        >
          <span className="min-w-0 truncate">{node.name}</span>
          <span className="shrink-0 text-[10px] text-omnix-text-dim">
            {formatSize(node.size)}
          </span>
        </button>
      </li>
    );
  }

  return (
    <li>
      <details open={path === ""}>
        <summary className="cursor-pointer rounded px-2 py-1 font-mono text-[11px] text-omnix-text-primary hover:bg-[rgba(99,102,241,0.08)]">
          {node.name}
        </summary>
        <ul className="ml-3 border-l border-[var(--omnix-shell-border)] pl-2">
          {(node.children ?? []).map((child) => (
            <TreeNode
              key={`${fullPath}/${child.name}`}
              node={child}
              path={fullPath}
              onOpenFile={onOpenFile}
            />
          ))}
        </ul>
      </details>
    </li>
  );
}

export function FilesDrawer({ workspaceId, onOpenFile }: Props) {
  const [tree, setTree] = useState<FileTreeNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void getFileTree(workspaceId)
      .then((next) => {
        if (!cancelled) setTree(next);
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : "load failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  if (loading) return <div className="p-4 text-sm text-omnix-text-dim">Loading files...</div>;
  if (err) return <div className="p-4 text-sm text-rose-300/90">Files load failed: {err}</div>;
  if (!tree) return <div className="p-4 text-sm text-omnix-text-dim">No files found.</div>;

  return (
    <div className="p-3">
      <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-omnix-text-dim">
        graph-aware tree
      </div>
      <ul>
        {(tree.children ?? []).map((child) => (
          <TreeNode
            key={child.name}
            node={child}
            path=""
            onOpenFile={(path) => {
              onOpenFile(path);
            }}
          />
        ))}
      </ul>
    </div>
  );
}
