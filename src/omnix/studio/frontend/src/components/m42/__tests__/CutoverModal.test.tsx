import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

vi.mock("@/lib/cutoverApi", async () => {
  return {
    SNAP_POINTS: [0, 1, 5, 10, 25, 50, 75, 100],
    snapTo: (v: number) => {
      const points = [0, 1, 5, 10, 25, 50, 75, 100];
      return points.reduce((best, p) => (Math.abs(v - p) < Math.abs(v - best) ? p : best));
    },
    getCutoverState: vi.fn(),
    previewShift: vi.fn(),
    confirmShift: vi.fn(),
    rollback: vi.fn(),
  };
});

import { CutoverModal } from "../CutoverModal";
import * as cutoverApi from "@/lib/cutoverApi";

/**
 * React 18 synthetic events listen to the native "input" event for change-style
 * inputs. Calling element.value = "..." doesn't notify React because React
 * caches the prior value internally. The standard workaround sets the value
 * via the native setter so React's value-tracker observes the change, then
 * dispatches a bubbling "input" event for React's delegated listener.
 */
function fireReactChange(
  el: HTMLInputElement | HTMLTextAreaElement,
  value: string
): void {
  const proto = el instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype
    : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  setter?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

const mocked = cutoverApi as unknown as {
  getCutoverState: ReturnType<typeof vi.fn>;
  previewShift: ReturnType<typeof vi.fn>;
  confirmShift: ReturnType<typeof vi.fn>;
  rollback: ReturnType<typeof vi.fn>;
};

function makeState(currentPct: number) {
  return {
    unit: "checkout",
    currentPct,
    history: [
      {
        ts: 1716_000_000,
        fromPct: 0,
        toPct: currentPct,
        receiptId: "rcpt-abc",
        receiptUrl: "/verify/r/rcpt-abc",
        operator: "ops@axiomcontrol.systems",
      },
    ],
  };
}

function makePreview(target: number) {
  return {
    unit_id: "checkout",
    tenant_id: "t1",
    previous_percentage: 0,
    target_percentage: target,
    verifier_summary: { scientist_mismatches: 0 },
    created_at_unix: 1716_000_500,
    kind: "cutover.authorization",
  };
}

describe("CutoverModal", () => {
  let container: HTMLDivElement;
  let root: Root;
  const onClose = vi.fn();

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    onClose.mockReset();
    mocked.getCutoverState.mockReset();
    mocked.previewShift.mockReset();
    mocked.confirmShift.mockReset();
    mocked.rollback.mockReset();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function mount(initialState = makeState(10)) {
    mocked.getCutoverState.mockResolvedValueOnce(initialState);
    await act(async () => {
      root.render(<CutoverModal unit="checkout" onClose={onClose} />);
    });
    await act(async () => {
      await Promise.resolve();
    });
  }

  it("renders current state from getCutoverState", async () => {
    await mount(makeState(25));
    const pct = container.querySelector('[data-testid="cutover-current-pct"]');
    expect(pct?.textContent).toContain("25%");
  });

  it("disables confirm until preview loaded", async () => {
    await mount();
    const confirm = container.querySelector(
      '[data-testid="cutover-confirm"]'
    ) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
  });

  it("slider change calls previewShift and renders preview JSON", async () => {
    await mount();
    mocked.previewShift.mockResolvedValueOnce({ receiptPreview: makePreview(50) });
    const slider = container.querySelector(
      '[data-testid="cutover-slider"]'
    ) as HTMLInputElement;
    await act(async () => {
      fireReactChange(slider, "50");
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(mocked.previewShift).toHaveBeenCalledWith("checkout", 50);
    const pre = container.querySelector('[data-testid="cutover-preview"]');
    expect(pre?.textContent).toContain('"target_percentage": 50');
  });

  it("confirm fires confirmShift with the preview and refreshes state", async () => {
    await mount();
    mocked.previewShift.mockResolvedValueOnce({ receiptPreview: makePreview(50) });
    mocked.confirmShift.mockResolvedValueOnce({ receiptId: "rcpt-new" });
    mocked.getCutoverState.mockResolvedValueOnce(makeState(50));

    const slider = container.querySelector(
      '[data-testid="cutover-slider"]'
    ) as HTMLInputElement;
    await act(async () => {
      fireReactChange(slider, "50");
    });
    await act(async () => {
      await Promise.resolve();
    });

    const confirm = container.querySelector(
      '[data-testid="cutover-confirm"]'
    ) as HTMLButtonElement;
    await act(async () => {
      confirm.click();
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mocked.confirmShift).toHaveBeenCalledWith(
      "checkout",
      50,
      expect.objectContaining({ target_percentage: 50 })
    );
  });

  it("rollback requires a reason and calls rollback API", async () => {
    await mount();
    const toggle = container.querySelector(
      '[data-testid="cutover-toggle-rollback"]'
    ) as HTMLButtonElement;
    await act(async () => {
      toggle.click();
    });
    const confirmBtn = container.querySelector(
      '[data-testid="cutover-rollback-confirm"]'
    ) as HTMLButtonElement;
    // With no reason, rollback button is disabled.
    expect(confirmBtn.disabled).toBe(true);

    const ta = container.querySelector(
      '[data-testid="cutover-rollback-reason"]'
    ) as HTMLTextAreaElement;
    await act(async () => {
      fireReactChange(ta, "verifier mismatch surfaced in prod");
    });
    // Re-query — React re-renders on every state change.
    const enabled = container.querySelector(
      '[data-testid="cutover-rollback-confirm"]'
    ) as HTMLButtonElement;
    expect(enabled.disabled).toBe(false);

    mocked.rollback.mockResolvedValueOnce({ receiptId: "rcpt-rollback" });
    mocked.getCutoverState.mockResolvedValueOnce(makeState(0));
    await act(async () => {
      enabled.click();
    });
    expect(mocked.rollback).toHaveBeenCalledWith("checkout", "verifier mismatch surfaced in prod");
  });

  it("history rows render with receipt links", async () => {
    await mount(makeState(25));
    const link = container.querySelector(
      '[data-testid="cutover-history-link-rcpt-abc"]'
    ) as HTMLAnchorElement;
    expect(link).toBeTruthy();
    expect(link.getAttribute("href")).toBe("/verify/r/rcpt-abc");
  });

  it("Escape key calls onClose", async () => {
    await mount();
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(onClose).toHaveBeenCalled();
  });
});
