import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReceiptsDrawer } from "../ReceiptsDrawer";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiMock = vi.hoisted(() => ({
  listReceipts: vi.fn(),
  getReceiptById: vi.fn(),
}));

const findingsMock = vi.hoisted(() => ({
  fetchFindingScans: vi.fn(),
  verifyScan: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    listReceipts: apiMock.listReceipts,
    getReceiptById: apiMock.getReceiptById,
  };
});

vi.mock("@/lib/findingsApi", () => ({
  fetchFindingScans: findingsMock.fetchFindingScans,
  verifyScan: findingsMock.verifyScan,
}));

function render(node: React.ReactElement): { root: Root; container: HTMLDivElement } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(node));
  return { root, container };
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function runDebounce() {
  await act(async () => {
    vi.advanceTimersByTime(150);
  });
  await flush();
}

beforeEach(() => {
  vi.useFakeTimers();
  findingsMock.fetchFindingScans.mockResolvedValue({ scans: [] });
  findingsMock.verifyScan.mockResolvedValue({
    verified: true,
    reason: "ok",
    scan_id: "2026-05-04T19-22-13Z_a3f9d712",
    finding_count: 1,
    manifest_summary: { finding_count: 1 },
  });
  apiMock.listReceipts.mockResolvedValue([
    {
      receipt_id: "call_ok",
      kind: "fabric.call",
      target: "openai",
      hash_prefix: "abcdef123456",
      sig_alg: "ML-DSA-65",
      has_signature: true,
      verified: true,
      mtime_iso: "2026-04-29T01:00:00Z",
      source: "fabric",
      path: "/tmp/call_ok.json",
    },
  ]);
  apiMock.getReceiptById.mockResolvedValue({ event: "fabric.call", call_id: "ok" });
});

afterEach(() => {
  document.body.textContent = "";
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("ReceiptsDrawer", () => {
  it("debounces receipt list refresh", async () => {
    render(<ReceiptsDrawer workspaceId="ws1" />);

    expect(apiMock.listReceipts).not.toHaveBeenCalled();
    await act(async () => {
      vi.advanceTimersByTime(149);
    });
    expect(apiMock.listReceipts).not.toHaveBeenCalled();

    await runDebounce();

    expect(apiMock.listReceipts).toHaveBeenCalledWith("ws1", { limit: 200 });
  });

  it("renders honest signature states", async () => {
    apiMock.listReceipts.mockResolvedValue([
      {
        receipt_id: "ok",
        kind: "fabric.call",
        target: "openai",
        hash_prefix: "okhash",
        sig_alg: "ML-DSA-65",
        has_signature: true,
        verified: true,
        mtime_iso: "2026-04-29T01:00:00Z",
        source: "fabric",
        path: "/tmp/ok.json",
      },
      {
        receipt_id: "bad",
        kind: "fabric.call",
        target: "anthropic",
        hash_prefix: "badhash",
        sig_alg: "ML-DSA-65",
        has_signature: true,
        verified: false,
        mtime_iso: "2026-04-29T01:01:00Z",
        source: "fabric",
        path: "/tmp/bad.json",
      },
      {
        receipt_id: "unsigned",
        kind: "vault.scan",
        target: "env",
        hash_prefix: "unsignedhash",
        sig_alg: "unsigned",
        has_signature: false,
        verified: false,
        mtime_iso: "2026-04-29T01:02:00Z",
        source: "scan",
        path: "/tmp/unsigned.json",
      },
    ]);
    const { container } = render(<ReceiptsDrawer workspaceId="ws1" />);

    await runDebounce();

    expect(container.textContent).toContain("verified");
    expect(container.textContent).toContain("signature invalid");
    expect(container.textContent).toContain("unsigned");
  });

  it("fetches full JSON only when a receipt expands", async () => {
    const { container } = render(<ReceiptsDrawer workspaceId="ws1" />);
    await runDebounce();

    expect(apiMock.getReceiptById).not.toHaveBeenCalled();
    const details = container.querySelector("details") as HTMLDetailsElement;
    await act(async () => {
      details.open = true;
      details.dispatchEvent(new Event("toggle", { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(apiMock.getReceiptById).toHaveBeenCalledWith("ws1", "call_ok");
    expect(container.querySelector("pre")?.textContent).toContain('"call_id": "ok"');
  });

  it("tab switch renders findings section", async () => {
    findingsMock.fetchFindingScans.mockResolvedValue({
      scans: [
        {
          scan_id: "2026-05-04T19-22-13Z_a3f9d712",
          scan_started_at: "2026-05-04T19:22:13.000Z",
          scan_finished_at: null,
          finding_count: 3,
          dir_path_relative: "findings/proj/2026-05-04T19-22-13Z_a3f9d712",
        },
      ],
    });
    const { container } = render(<ReceiptsDrawer workspaceId="ws1" />);
    await runDebounce();

    const findingsTab = container.querySelector(
      '[data-testid="tab-finding-scans"]',
    ) as HTMLButtonElement | null;
    expect(findingsTab).toBeTruthy();

    await act(async () => {
      findingsTab!.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(findingsMock.fetchFindingScans).toHaveBeenCalled();
    expect(container.textContent).toContain("2026-05-04");
    expect(container.textContent).toContain("findings");
  });

  it("verify scan button calls API and renders badge", async () => {
    const sid = "2026-05-04T19-22-13Z_a3f9d712";
    findingsMock.fetchFindingScans.mockResolvedValue({
      scans: [
        {
          scan_id: sid,
          scan_started_at: "2026-05-04T19:22:13.000Z",
          scan_finished_at: null,
          finding_count: 2,
          dir_path_relative: `findings/x/${sid}`,
        },
      ],
    });
    findingsMock.verifyScan.mockResolvedValue({
      verified: true,
      reason: "ok",
      scan_id: sid,
      finding_count: 2,
      manifest_summary: { finding_count: 2, merkle_root: "abc" },
    });

    const { container } = render(<ReceiptsDrawer workspaceId="ws1" />);
    await runDebounce();

    await act(async () => {
      (container.querySelector('[data-testid="tab-finding-scans"]') as HTMLButtonElement).click();
      await Promise.resolve();
      await Promise.resolve();
    });

    const btn = container.querySelector(`[data-testid="verify-scan-${sid}"]`) as HTMLButtonElement | null;
    expect(btn).toBeTruthy();

    await act(async () => {
      btn!.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(findingsMock.verifyScan).toHaveBeenCalledWith(sid);
    expect(container.textContent).toContain("verified");
  });
});
