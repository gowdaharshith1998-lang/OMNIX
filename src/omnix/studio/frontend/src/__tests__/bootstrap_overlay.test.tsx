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
      canGoBack: () => false,
      goBack: vi.fn(),
      applyScopeNavigation: vi.fn(),
      simulateRenderError: vi.fn(),
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

import { Workspace } from "@/components/Workspace";

function findBootstrapOverlay(): HTMLElement | null {
  const el = document.querySelector("[data-omnix-bootstrap-overlay]");
  return el instanceof HTMLElement ? el : null;
}

const initialStats = {
  files: 3,
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

describe("bootstrap overlay", () => {
  beforeEach(() => {
    wsHarness.reset();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.replaceChildren();
  });

  it("overlay visible when bootstrap_start received (file count)", async () => {
    const root = renderWorkspace();
    await act(async () => {
      await Promise.resolve();
    });

    const onMessage = wsHarness.lastOnMessage!;
    await act(async () => {
      onMessage({
        type: "bootstrap_start",
        ts: 0,
        workspace_id: "ws-test",
        total_files: 42,
        mode: "existing",
      });
    });

    const overlay = findBootstrapOverlay();
    expect(overlay).not.toBeNull();
    expect(overlay?.textContent).toContain("Building graph from 42 files");

    await act(async () => {
      onMessage({
        type: "bootstrap_complete",
        duration_ms: 1,
        total_nodes: 0,
        total_edges: 0,
      });
    });

    await act(async () => {
      vi.advanceTimersByTime(320);
    });

    expect(findBootstrapOverlay()).toBeNull();

    act(() => {
      root.unmount();
    });
  });

  it("fallback copy when file count unknown", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    act(() => {
      root.render(
        React.createElement(Workspace, {
          workspaceId: "ws-test",
          projectPath: "/tmp/proj",
          initialStats: { files: 0, functions: 0, classes: 0, edges: 0 },
          onBack: () => {},
        })
      );
    });
    await act(async () => {
      await Promise.resolve();
    });

    const onMessage = wsHarness.lastOnMessage!;
    await act(async () => {
      onMessage({
        type: "bootstrap_start",
        ts: 0,
        workspace_id: "ws-test",
        total_files: 0,
        mode: "scratch",
      });
    });

    const overlay = findBootstrapOverlay();
    expect(overlay?.textContent).toContain("your workspace");

    act(() => {
      root.unmount();
    });
  });

  it("overlay hidden ~300ms after bootstrap_complete", async () => {
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

    expect(findBootstrapOverlay()).not.toBeNull();

    await act(async () => {
      vi.advanceTimersByTime(299);
    });
    expect(findBootstrapOverlay()).not.toBeNull();

    await act(async () => {
      vi.advanceTimersByTime(2);
    });
    expect(findBootstrapOverlay()).toBeNull();

    act(() => {
      root.unmount();
    });
  });

  it("does not show overlay on reconnect bootstrap", async () => {
    const root = renderWorkspace();
    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      wsHarness.lastOnMessage!({
        type: "bootstrap_complete",
        duration_ms: 1,
        total_nodes: 0,
        total_edges: 0,
      });
    });
    await act(async () => {
      vi.advanceTimersByTime(320);
    });
    expect(findBootstrapOverlay()).toBeNull();

    await act(async () => {
      wsHarness.latest!.close();
    });
    await act(async () => {
      wsHarness.latest!.emitConnecting();
    });
    await act(async () => {
      wsHarness.latest!.emitOpen();
    });

    await act(async () => {
      wsHarness.lastOnMessage!({
        type: "bootstrap_start",
        ts: 0,
        workspace_id: "ws-test",
        total_files: 99,
        mode: "existing",
      });
    });

    expect(findBootstrapOverlay()).toBeNull();

    act(() => {
      root.unmount();
    });
  });

  it("overlay does not block pointer events (X-Ray remains interactable)", async () => {
    const root = renderWorkspace();
    await act(async () => {
      await Promise.resolve();
    });

    const overlay = findBootstrapOverlay();
    expect(overlay).not.toBeNull();
    expect(overlay?.className).toMatch(/pointer-events-none/);

    act(() => {
      root.unmount();
    });
  });
});
