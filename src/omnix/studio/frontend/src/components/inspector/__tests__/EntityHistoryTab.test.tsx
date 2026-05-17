import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

import { __resetWireEventsForTests, pushWireEvent } from "@/lib/wireEventBuffer";
import type { WireEvent } from "../AgentTab";
import { EntityHistoryTab } from "../EntityHistoryTab";

const roots: Root[] = [];

function render(node: React.ReactElement): { root: Root; container: HTMLDivElement } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  roots.push(root);
  act(() => root.render(node));
  return { root, container };
}

afterEach(() => {
  act(() => {
    for (const root of roots.splice(0)) root.unmount();
  });
  document.body.textContent = "";
  __resetWireEventsForTests("w");
});

function w(type: WireEvent["type"], ts: number, targetId: string): WireEvent {
  return {
    id: `${type}:${targetId}:${ts}`,
    type,
    ts,
    actor: null,
    targetId,
    targetType: "code",
    confidence: null,
  };
}

describe("EntityHistoryTab", () => {
  it("renders empty state when no history", () => {
    const { container } = render(<EntityHistoryTab workspaceId="w" selectedEntityId={null} />);
    expect(container.textContent).toContain("No history yet");
  });

  it("renders chronologically (newest first)", async () => {
    const { container } = render(<EntityHistoryTab workspaceId="w" selectedEntityId={null} />);
    await act(async () => {
      pushWireEvent("w", w("node_added", Date.now() - 10_000, "a"));
      pushWireEvent("w", w("node_added", Date.now() - 5_000, "b"));
    });
    const rows = Array.from(container.querySelectorAll("[data-history-row]"));
    expect(rows.length).toBe(2);
    expect(rows[0]?.getAttribute("data-target-id")).toBe("b");
  });

  it("groups by day separators", async () => {
    const { container } = render(<EntityHistoryTab workspaceId="w" selectedEntityId={null} />);
    const day1 = new Date("2026-05-04T01:00:00Z").getTime();
    const day2 = new Date("2026-05-05T01:00:00Z").getTime();
    await act(async () => {
      pushWireEvent("w", w("node_added", day1, "a"));
      pushWireEvent("w", w("node_added", day2, "b"));
    });
    expect(container.querySelectorAll("[data-history-day]").length).toBeGreaterThan(1);
  });

  it("filters to selected entity when selectedEntityId is set", async () => {
    const { container } = render(<EntityHistoryTab workspaceId="w" selectedEntityId="n1" />);
    await act(async () => {
      pushWireEvent("w", w("node_modified", Date.now(), "n1"));
      pushWireEvent("w", w("node_modified", Date.now(), "n2"));
    });
    expect(container.querySelectorAll("[data-history-row]").length).toBe(1);
    expect(container.textContent).toContain("n1");
    expect(container.textContent).not.toContain("n2");
  });

  it("shows global scope when no entity selected", async () => {
    const { container } = render(<EntityHistoryTab workspaceId="w" selectedEntityId={null} />);
    await act(async () => {
      pushWireEvent("w", w("node_modified", Date.now(), "n1"));
      pushWireEvent("w", w("edge_added", Date.now(), "e1"));
    });
    expect(container.querySelectorAll("[data-history-row]").length).toBe(2);
  });

  it("does not render more than buffer size", async () => {
    const { container } = render(<EntityHistoryTab workspaceId="w" selectedEntityId={null} />);
    await act(async () => {
      for (let i = 0; i < 250; i++) {
        pushWireEvent("w", w("node_added", Date.now() - i, `n${i}`));
      }
    });
    expect(container.querySelectorAll("[data-history-row]").length).toBeLessThanOrEqual(200);
  });
});

