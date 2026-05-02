import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GrammarHealthDrawer } from "../GrammarHealthDrawer";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const grammarMock = vi.hoisted(() => ({
  fetchGrammarStatus: vi.fn(),
  fetchMutations: vi.fn(),
  fetchUnknownExtensions: vi.fn(),
  fetchLlmBudget: vi.fn(),
  verifyReceipt: vi.fn(),
}));

vi.mock("@/lib/grammarApi", () => ({
  fetchGrammarStatus: grammarMock.fetchGrammarStatus,
  fetchMutations: grammarMock.fetchMutations,
  fetchUnknownExtensions: grammarMock.fetchUnknownExtensions,
  fetchLlmBudget: grammarMock.fetchLlmBudget,
  verifyReceipt: grammarMock.verifyReceipt,
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

beforeEach(() => {
  grammarMock.fetchGrammarStatus.mockResolvedValue({
    grammars: [
      {
        grammar_name: "python",
        files_parsed: 10,
        avg_quality: 0.75,
        parse_modes: {},
        active_patterns: 2,
        recent_mutations_30d: 1,
        last_evolution_receipt: "/home/u/.omnix/receipts/ev.json",
      },
    ],
  });
  grammarMock.fetchMutations.mockResolvedValue({
    mutations: [
      {
        grammar_name: "python",
        action: "promote",
        node_type: "reason text here",
        observed_at: "2026-05-01T12:00:00Z",
        receipt_path: "/r.json",
        sig_path: "",
        receipt_exists: true,
        sig_exists: false,
      },
    ],
  });
  grammarMock.fetchUnknownExtensions.mockResolvedValue({
    extensions: [{ ext: ".foo", first_seen_at: "2026-01-01T00:00:00Z" }],
    total: 1,
  });
  grammarMock.fetchLlmBudget.mockResolvedValue({
    budget_total: null,
    budget_remaining: null,
    calls_today: null,
    available: false,
  });
  grammarMock.verifyReceipt.mockResolvedValue({
    verified: true,
    verifier_output: "ok",
  });
});

afterEach(() => {
  document.body.textContent = "";
  vi.clearAllMocks();
});

describe("GrammarHealthDrawer", () => {
  it("shows skeletons then grammar rows and poll fetches", async () => {
    const { container } = render(<GrammarHealthDrawer />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
    await flush();
    expect(container.textContent).toContain("python");
    expect(container.textContent).toContain("LLM budget: not configured");
    expect(grammarMock.fetchGrammarStatus).toHaveBeenCalled();
    expect(grammarMock.fetchMutations).toHaveBeenCalled();
    expect(grammarMock.fetchUnknownExtensions).toHaveBeenCalled();
    expect(grammarMock.fetchLlmBudget).toHaveBeenCalled();
  });

  it("renders per-section error without throwing away other sections", async () => {
    grammarMock.fetchGrammarStatus.mockRejectedValue(new Error("db missing"));
    const { container } = render(<GrammarHealthDrawer />);
    await flush();
    expect(container.textContent).toContain("Failed to load grammars");
    expect(container.textContent).toContain("promote");
    expect(container.textContent).toContain(".foo");
  });

  it("verify receipt shows checkmark after success", async () => {
    const { container } = render(<GrammarHealthDrawer />);
    await flush();
    const buttons = [...container.querySelectorAll("button")].filter(
      (b) => b.textContent === "Verify"
    );
    expect(buttons.length).toBeGreaterThan(0);
    act(() => {
      buttons[0]!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();
    expect(grammarMock.verifyReceipt).toHaveBeenCalled();
    expect(container.textContent).toContain("✓");
  });

  it("empty mutations list shows empty state when API returns []", async () => {
    grammarMock.fetchMutations.mockResolvedValue({ mutations: [] });
    const { container } = render(<GrammarHealthDrawer />);
    await flush();
    expect(container.textContent).toContain("No mutations recorded.");
  });
});
