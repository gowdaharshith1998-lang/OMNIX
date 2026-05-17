import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiMock = vi.hoisted(() => ({
  listReceipts: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    listReceipts: apiMock.listReceipts,
  };
});

import { ReceiptsTab } from "../ReceiptsTab";

const roots: Root[] = [];

function render(node: React.ReactElement): { root: Root; container: HTMLDivElement } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  roots.push(root);
  act(() => root.render(node));
  return { root, container };
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

afterEach(() => {
  act(() => {
    for (const root of roots.splice(0)) root.unmount();
  });
  document.body.textContent = "";
  vi.clearAllMocks();
});

describe("ReceiptsTab", () => {
  it("renders empty state when no receipts", async () => {
    apiMock.listReceipts.mockResolvedValueOnce([]);
    const { container } = render(<ReceiptsTab workspaceId="w" />);
    await flush();
    expect(container.textContent).toContain("No receipts yet");
  });

  it("renders list when receipts present", async () => {
    apiMock.listReceipts.mockResolvedValueOnce([
      {
        receipt_id: "r1",
        kind: "scan.manifest",
        target: "repo",
        hash_prefix: "abc123",
        sig_alg: "ML-DSA-65",
        has_signature: true,
        verified: false,
        mtime_iso: "2026-05-05T00:00:00Z",
        source: "scan",
        path: "/tmp/r1.json",
      },
      {
        receipt_id: "r2",
        kind: "finding",
        target: "services/governance.py",
        hash_prefix: "def456",
        sig_alg: "ed25519",
        has_signature: true,
        verified: true,
        mtime_iso: "2026-05-05T01:00:00Z",
        source: "scan",
        path: "/tmp/r2.json",
      },
      {
        receipt_id: "r3",
        kind: "fabric.call",
        target: "openai",
        hash_prefix: "zzz999",
        sig_alg: "unsigned",
        has_signature: false,
        verified: false,
        mtime_iso: "2026-05-05T02:00:00Z",
        source: "fabric",
        path: "/tmp/r3.json",
      },
    ]);
    const { container } = render(<ReceiptsTab workspaceId="w" />);
    await flush();
    expect(container.querySelectorAll("[data-receipt-row]").length).toBe(3);
  });

  it("shows id, timestamp, scheme", async () => {
    apiMock.listReceipts.mockResolvedValueOnce([
      {
        receipt_id: "rid",
        kind: "scan.manifest",
        target: "repo",
        hash_prefix: "abc123",
        sig_alg: "ML-DSA-65",
        has_signature: true,
        verified: false,
        mtime_iso: "2026-05-05T00:00:00Z",
        source: "scan",
        path: "/tmp/r.json",
      },
    ]);
    const { container } = render(<ReceiptsTab workspaceId="w" />);
    await flush();
    expect(container.textContent).toContain("rid");
    expect(container.querySelector("[data-receipt-ts]")?.textContent?.length).toBeTruthy();
    expect(container.textContent?.toLowerCase()).toContain("ml-dsa-65");
  });

  it("shows verify-status indicator (unknown/verified/unverified)", async () => {
    apiMock.listReceipts.mockResolvedValueOnce([
      {
        receipt_id: "ok",
        kind: "scan.manifest",
        target: "repo",
        hash_prefix: "ok",
        sig_alg: "ML-DSA-65",
        has_signature: true,
        verified: true,
        mtime_iso: "2026-05-05T00:00:00Z",
        source: "scan",
        path: "/tmp/ok.json",
      },
      {
        receipt_id: "bad",
        kind: "scan.manifest",
        target: "repo",
        hash_prefix: "bad",
        sig_alg: "ML-DSA-65",
        has_signature: true,
        verified: false,
        mtime_iso: "2026-05-05T00:00:00Z",
        source: "scan",
        path: "/tmp/bad.json",
      },
    ]);
    const { container } = render(<ReceiptsTab workspaceId="w" />);
    await flush();
    expect(container.textContent).toContain("verified");
    expect(container.textContent).toContain("unverified");
  });

  it("loads from endpoint on mount", async () => {
    apiMock.listReceipts.mockResolvedValueOnce([]);
    render(<ReceiptsTab workspaceId="w" />);
    await flush();
    expect(apiMock.listReceipts).toHaveBeenCalledWith("w", { limit: 100 });
  });

  it("handles endpoint error gracefully", async () => {
    apiMock.listReceipts.mockRejectedValueOnce(new Error("boom"));
    const { container } = render(<ReceiptsTab workspaceId="w" />);
    await flush();
    expect(container.textContent).toContain("Could not load receipts");
  });

  it("limits to at most 100 receipts", async () => {
    apiMock.listReceipts.mockResolvedValueOnce(
      Array.from({ length: 250 }, (_, i) => ({
        receipt_id: `r${i}`,
        kind: "scan.manifest",
        target: "repo",
        hash_prefix: "x",
        sig_alg: "ML-DSA-65",
        has_signature: true,
        verified: false,
        mtime_iso: "2026-05-05T00:00:00Z",
        source: "scan",
        path: `/tmp/r${i}.json`,
      }))
    );
    const { container } = render(<ReceiptsTab workspaceId="w" />);
    await flush();
    expect(container.querySelectorAll("[data-receipt-row]").length).toBe(100);
  });
});

