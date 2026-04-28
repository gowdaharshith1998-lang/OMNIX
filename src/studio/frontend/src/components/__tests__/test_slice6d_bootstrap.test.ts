import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const wsHarness = vi.hoisted(() => {
  let latest: {
    connect: () => void;
    close: () => void;
    emitConnecting: () => void;
    emitOpen: () => void;
  } | null = null;
  let lastOnMessage: ((msg: Record<string, unknown>) => void) | undefined;
  return {
    get latest() {
      return latest;
    },
    get lastOnMessage() {
      return lastOnMessage;
    },
    reset() {
      latest = null;
      lastOnMessage = undefined;
    },
    capture(
      onMessage: (msg: Record<string, unknown>) => void,
      api: {
        connect: () => void;
        close: () => void;
        emitConnecting: () => void;
        emitOpen: () => void;
      }
    ) {
      lastOnMessage = onMessage;
      latest = api;
    },
  };
});

vi.mock("@/lib/ws", () => ({
  StudioWebSocket: vi.fn(function StudioWebSocket(
    _workspaceId: string,
    onMessage: (msg: Record<string, unknown>) => void,
    onState?: (s: "connecting" | "open" | "closed") => void
  ) {
    const emit = onState ?? (() => {});
    const api = {
      connect: () => {
        emit("connecting");
        emit("open");
      },
      close: () => {
        emit("closed");
      },
      emitConnecting: () => {
        emit("connecting");
      },
      emitOpen: () => {
        emit("open");
      },
    };
    wsHarness.capture(onMessage, api);
    return api;
  }),
}));

vi.mock("@/components/Graph/GraphCanvas", () => ({
  GraphCanvas: React.forwardRef(function MockGraphCanvas(
    _props: unknown,
    ref: React.Ref<{ ingestMessage: (msg: unknown) => void }>
  ) {
    React.useImperativeHandle(ref, () => ({
      ingestMessage: vi.fn(),
    }));
    return React.createElement("div", { "data-testid": "graph-canvas" });
  }),
}));

vi.mock("@/lib/api", () => ({
  listFiles: vi.fn(() => Promise.resolve([])),
  createFile: vi.fn(),
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

import { Workspace } from "../Workspace";

function findLoadingOverlay(): Element | null {
  for (const el of document.body.querySelectorAll('[aria-live="polite"]')) {
    if (el.textContent?.includes("loading workspace")) return el;
  }
  return null;
}

const initialStats = {
  files: 1,
  functions: 0,
  classes: 0,
  edges: 0,
};

function renderWorkspace(): Root {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      React.createElement(Workspace, {
        workspaceId: "ws-test",
        projectPath: "/tmp/proj",
        initialStats,
        onBack: () => {},
      })
    );
  });
  return root;
}

describe("slice 6d bootstrap overlay (Option A)", () => {
  beforeEach(() => {
    wsHarness.reset();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.replaceChildren();
  });

  it("shows overlay during initial connect/open before bootstrap_complete, then removes after fade", async () => {
    const root = renderWorkspace();
    await act(async () => {
      await Promise.resolve();
    });

    expect(document.body.textContent).toContain("loading workspace…");

    const onMessage = wsHarness.lastOnMessage!;
    await act(async () => {
      onMessage({
        type: "bootstrap_complete",
        duration_ms: 1,
        total_nodes: 0,
        total_edges: 0,
      });
    });

    const pill = findLoadingOverlay();
    expect(pill?.className).toMatch(/opacity-0/);

    await act(async () => {
      vi.advanceTimersByTime(200);
    });

    expect(document.body.textContent).not.toContain("loading workspace…");

    act(() => {
      root.unmount();
    });
  });

  it("does not show bootstrap overlay while reconnecting (closed/connecting with prior open)", async () => {
    const root = renderWorkspace();
    await act(async () => {
      await Promise.resolve();
    });

    expect(document.body.textContent).toContain("loading workspace…");

    await act(async () => {
      wsHarness.lastOnMessage!({
        type: "bootstrap_complete",
        duration_ms: 1,
        total_nodes: 0,
        total_edges: 0,
      });
    });
    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    expect(findLoadingOverlay()).toBeNull();

    await act(async () => {
      wsHarness.latest!.close();
    });
    expect(findLoadingOverlay()).toBeNull();

    await act(async () => {
      wsHarness.latest!.emitConnecting();
    });
    expect(findLoadingOverlay()).toBeNull();

    await act(async () => {
      wsHarness.latest!.emitOpen();
    });
    expect(findLoadingOverlay()).toBeNull();

    act(() => {
      root.unmount();
    });
  });

  it("applies hiding opacity before timer clears the overlay", async () => {
    const root = renderWorkspace();
    await act(async () => {
      await Promise.resolve();
    });

    const onMessage = wsHarness.lastOnMessage!;
    await act(async () => {
      onMessage({
        type: "bootstrap_complete",
        duration_ms: 1,
        total_nodes: 0,
        total_edges: 0,
      });
    });

    const pill = findLoadingOverlay();
    expect(pill?.className).toMatch(/opacity-0/);
    expect(pill?.className).toMatch(/duration-200/);

    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    expect(findLoadingOverlay()).toBeNull();

    act(() => {
      root.unmount();
    });
  });
});
