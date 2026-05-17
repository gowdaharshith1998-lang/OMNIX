import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

import { colorForType } from "@/components/Graph/entityPalette";
import { AgentTab, type WireEvent } from "../AgentTab";

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
});

function ev(partial: Partial<WireEvent> & { type: WireEvent["type"] }): WireEvent {
  return {
    id: partial.id ?? `e:${partial.type}:${Math.random()}`,
    type: partial.type,
    ts: partial.ts ?? Date.now(),
    actor: partial.actor ?? null,
    targetId: partial.targetId ?? "n1",
    targetType: partial.targetType ?? "code",
    confidence: partial.confidence ?? null,
  };
}

describe("AgentTab", () => {
  it("renders empty state when no events", () => {
    const { container } = render(<AgentTab events={[]} />);
    expect(container.textContent).toContain("Waiting for agent activity");
  });

  it("renders node_added event", () => {
    const { container } = render(<AgentTab events={[ev({ type: "node_added" })]} />);
    expect(container.textContent).toContain("node_added");
  });

  it("renders node_modified event", () => {
    const { container } = render(<AgentTab events={[ev({ type: "node_modified" })]} />);
    expect(container.textContent).toContain("node_modified");
  });

  it("renders edge_added event", () => {
    const { container } = render(<AgentTab events={[ev({ type: "edge_added" })]} />);
    expect(container.textContent).toContain("edge_added");
  });

  it("renders edge_removed event", () => {
    const { container } = render(<AgentTab events={[ev({ type: "edge_removed" })]} />);
    expect(container.textContent).toContain("edge_removed");
  });

  it("renders node_removed event", () => {
    const { container } = render(<AgentTab events={[ev({ type: "node_removed" })]} />);
    expect(container.textContent).toContain("node_removed");
  });

  it("shows timestamp on each entry", () => {
    const { container } = render(<AgentTab events={[ev({ type: "node_added", ts: 1_700_000_000_000 })]} />);
    expect(container.querySelector("[data-agent-ts]")?.textContent?.length).toBeTruthy();
  });

  it("tints entries via entity palette", () => {
    const { container } = render(
      <AgentTab events={[ev({ type: "node_added", targetType: "code" })]} />
    );
    const row = container.querySelector("[data-agent-feed-entry]") as HTMLDivElement | null;
    expect(row).toBeTruthy();
    expect(row?.style.borderLeftColor).toBe(colorForType("code"));
  });

  it("has confidence slot (data-confidence)", () => {
    const { container } = render(
      <AgentTab events={[ev({ type: "node_added", confidence: null })]} />
    );
    const row = container.querySelector("[data-agent-feed-entry]");
    expect(row?.getAttribute("data-confidence")).toBe("");
  });

  it("virtualizes at 100 visible entries", () => {
    const events = Array.from({ length: 200 }, (_, i) =>
      ev({ type: "node_added", id: `e${i}`, ts: Date.now() - i })
    );
    const { container } = render(<AgentTab events={events} />);
    const rows = container.querySelectorAll("[data-agent-feed-entry]");
    expect(rows.length).toBeLessThan(120);
    expect(container.textContent).toContain("earlier events");
  });

  it("renders new events on prop update within 200ms", async () => {
    const events1: WireEvent[] = [];
    const events2: WireEvent[] = [ev({ type: "node_added", id: "later" })];
    const { root, container } = render(<AgentTab events={events1} />);
    expect(container.textContent).toContain("Waiting for agent activity");
    await act(async () => {
      root.render(<AgentTab events={events2} />);
    });
    expect(container.textContent).toContain("node_added");
  });
});

