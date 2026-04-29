import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReceiptsDrawer } from "../ReceiptsDrawer";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiMock = vi.hoisted(() => ({
  listReceipts: vi.fn(),
  getReceiptById: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    listReceipts: apiMock.listReceipts,
    getReceiptById: apiMock.getReceiptById,
  };
});

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
});
